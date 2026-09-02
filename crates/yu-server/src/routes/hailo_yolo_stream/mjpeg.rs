use std::{
    collections::HashMap,
    convert::Infallible,
    future::Future,
    pin::Pin,
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Mutex, RwLock,
    },
    time::{Duration, Instant},
};

use axum::{
    body::Body,
    http::{header, StatusCode},
    response::Response,
};
use bytes::{Bytes, BytesMut};
use futures_util::stream;
use image::{codecs::jpeg::JpegEncoder as ImageJpegEncoder, ExtendedColorType};
use tokio::sync::{broadcast, watch, Notify, Semaphore};

use super::{
    detect::DetectPipeline,
    draw::{draw_detections, DrawnFrame},
    source_task::{SourceHandle, SourceState, SourceStatus},
};

pub(crate) const CONTENT_TYPE: &str = "multipart/x-mixed-replace; boundary=frame";
const JPEG_QUALITY: u8 = 70;
const MAX_FPS: u32 = 15;
const FRAME_INTERVAL: Duration = Duration::from_nanos(1_000_000_000 / MAX_FPS as u64 + 1);
const ENCODE_CONCURRENCY: usize = 2;
const BROADCAST_CAPACITY: usize = 2;
const MAX_VIEWERS: usize = 4;

trait Encoder: Send + Sync {
    fn encode(&self, frame: &DrawnFrame, quality: u8) -> Result<Bytes, String>;
}

struct CpuEncoder;

impl Encoder for CpuEncoder {
    fn encode(&self, frame: &DrawnFrame, quality: u8) -> Result<Bytes, String> {
        encode_jpeg(&frame.bytes, frame.width, frame.height, quality)
    }
}

pub(crate) fn encode_jpeg(
    bytes: &[u8],
    width: u32,
    height: u32,
    quality: u8,
) -> Result<Bytes, String> {
    let mut rgb = bytes.to_vec();
    for pixel in rgb.as_chunks_mut::<3>().0 {
        pixel.swap(0, 2);
    }
    let mut jpeg = Vec::new();
    ImageJpegEncoder::new_with_quality(&mut jpeg, quality)
        .encode(&rgb, width, height, ExtendedColorType::Rgb8)
        .map_err(|error| error.to_string())?;
    Ok(Bytes::from(jpeg))
}

trait Clock: Send + Sync {
    fn now(&self) -> Duration;
    fn sleep_until(&self, deadline: Duration) -> Pin<Box<dyn Future<Output = ()> + Send + '_>>;
}

struct SystemClock {
    origin: Instant,
}

impl Default for SystemClock {
    fn default() -> Self {
        Self {
            origin: Instant::now(),
        }
    }
}

impl Clock for SystemClock {
    fn now(&self) -> Duration {
        self.origin.elapsed()
    }

    fn sleep_until(&self, deadline: Duration) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
        let delay = deadline.saturating_sub(self.now());
        Box::pin(tokio::time::sleep(delay))
    }
}

struct PendingFrame {
    bytes: Arc<Bytes>,
    width: u32,
    height: u32,
    generation: u64,
}

#[derive(Default)]
struct EncodeSlot {
    pending: tokio::sync::Mutex<Option<PendingFrame>>,
    notify: Notify,
    closed: AtomicBool,
}

struct SourceStream {
    sender: Mutex<Option<broadcast::Sender<Arc<Bytes>>>>,
    viewers: AtomicUsize,
    generation: AtomicU64,
    active: AtomicBool,
    slot: Arc<EncodeSlot>,
    latest_drawn: RwLock<Option<Arc<DrawnFrame>>>,
}

impl SourceStream {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            sender: Mutex::new(None),
            viewers: AtomicUsize::new(0),
            generation: AtomicU64::new(0),
            active: AtomicBool::new(false),
            slot: Arc::new(EncodeSlot::default()),
            latest_drawn: RwLock::new(None),
        })
    }

    fn start(&self) {
        let mut sender = self
            .sender
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if self.active.swap(true, Ordering::AcqRel) {
            return;
        }
        self.generation.fetch_add(1, Ordering::AcqRel);
        let (next, _) = broadcast::channel(BROADCAST_CAPACITY);
        *sender = Some(next);
        *self
            .latest_drawn
            .write()
            .unwrap_or_else(|error| error.into_inner()) = None;
        self.slot.notify.notify_waiters();
    }

    async fn stop(&self) {
        {
            let mut sender = self
                .sender
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            if !self.active.swap(false, Ordering::AcqRel) && sender.is_none() {
                return;
            }
            self.generation.fetch_add(1, Ordering::AcqRel);
            sender.take();
        }
        self.slot.pending.lock().await.take();
        *self
            .latest_drawn
            .write()
            .unwrap_or_else(|error| error.into_inner()) = None;
        self.slot.notify.notify_waiters();
    }

    async fn close(&self) {
        self.stop().await;
        self.slot.closed.store(true, Ordering::Release);
        self.slot.notify.notify_waiters();
    }

    fn body(self: &Arc<Self>) -> Body {
        let receiver = {
            let sender = self
                .sender
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            if !self.active.load(Ordering::Acquire) {
                return Body::empty();
            }
            let Some(sender) = sender.as_ref() else {
                return Body::empty();
            };
            if !self.try_add_viewer() {
                return Body::empty();
            }
            sender.subscribe()
        };
        let state = ViewerState {
            receiver,
            _lease: ViewerLease(Arc::clone(self)),
        };
        Body::from_stream(stream::unfold(state, |mut state| async move {
            loop {
                match state.receiver.recv().await {
                    Ok(jpeg) => return Some((Ok::<_, Infallible>(multipart_part(&jpeg)), state)),
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(broadcast::error::RecvError::Closed) => return None,
                }
            }
        }))
    }

    fn response(self: &Arc<Self>) -> Response {
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, CONTENT_TYPE)
            .body(self.body())
            .expect("static MJPEG response is valid")
    }

    fn try_add_viewer(&self) -> bool {
        let mut current = self.viewers.load(Ordering::Acquire);
        loop {
            if current >= MAX_VIEWERS {
                return false;
            }
            match self.viewers.compare_exchange_weak(
                current,
                current + 1,
                Ordering::AcqRel,
                Ordering::Acquire,
            ) {
                Ok(_) => return true,
                Err(next) => current = next,
            }
        }
    }

    fn viewer_count(&self) -> usize {
        self.viewers.load(Ordering::Acquire)
    }

    fn latest_drawn(&self) -> Option<Arc<DrawnFrame>> {
        self.latest_drawn
            .read()
            .unwrap_or_else(|error| error.into_inner())
            .clone()
    }

    fn publish(&self, generation: u64, drawn: Arc<DrawnFrame>, jpeg: Bytes) {
        let sender = self
            .sender
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if !self.active.load(Ordering::Acquire)
            || self.generation.load(Ordering::Acquire) != generation
        {
            return;
        }
        *self
            .latest_drawn
            .write()
            .unwrap_or_else(|error| error.into_inner()) = Some(drawn);
        if let Some(sender) = sender.as_ref() {
            let _ = sender.send(Arc::new(jpeg));
        }
    }
}

struct ViewerState {
    receiver: broadcast::Receiver<Arc<Bytes>>,
    _lease: ViewerLease,
}

struct ViewerLease(Arc<SourceStream>);

impl Drop for ViewerLease {
    fn drop(&mut self) {
        self.0.viewers.fetch_sub(1, Ordering::AcqRel);
    }
}

struct HubInner {
    sources: RwLock<HashMap<String, Arc<SourceStream>>>,
    semaphore: Arc<Semaphore>,
    encoder: Arc<dyn Encoder>,
    clock: Arc<dyn Clock>,
    closed: AtomicBool,
}

#[derive(Clone)]
pub(crate) struct MjpegHub {
    inner: Arc<HubInner>,
}

impl Default for MjpegHub {
    fn default() -> Self {
        Self::new()
    }
}

impl MjpegHub {
    pub(crate) fn new() -> Self {
        Self::with_components(Arc::new(CpuEncoder), Arc::new(SystemClock::default()))
    }

    fn with_components(encoder: Arc<dyn Encoder>, clock: Arc<dyn Clock>) -> Self {
        Self {
            inner: Arc::new(HubInner {
                sources: RwLock::new(HashMap::new()),
                semaphore: Arc::new(Semaphore::new(ENCODE_CONCURRENCY)),
                encoder,
                clock,
                closed: AtomicBool::new(false),
            }),
        }
    }

    pub(crate) fn attach(
        &self,
        source_id: String,
        handle: &SourceHandle,
        detector: DetectPipeline,
    ) {
        self.attach_receivers(
            source_id,
            handle.frames_tx.subscribe(),
            handle.status_rx.clone(),
            detector,
        );
    }

    fn attach_receivers(
        &self,
        source_id: String,
        frames: broadcast::Receiver<Arc<Bytes>>,
        status: watch::Receiver<SourceStatus>,
        detector: DetectPipeline,
    ) -> Arc<SourceStream> {
        let source = SourceStream::new();
        if self.inner.closed.load(Ordering::Acquire) {
            source.slot.closed.store(true, Ordering::Release);
        }
        if let Some(old) = self
            .inner
            .sources
            .write()
            .unwrap_or_else(|error| error.into_inner())
            .insert(source_id.clone(), Arc::clone(&source))
        {
            tokio::spawn(async move { old.close().await });
        }
        tokio::spawn(produce(Arc::clone(&source), frames, status));
        tokio::spawn(consume(
            source_id,
            Arc::clone(&source),
            detector,
            Arc::clone(&self.inner.semaphore),
            Arc::clone(&self.inner.encoder),
            Arc::clone(&self.inner.clock),
        ));
        source
    }

    pub(crate) fn start_source(&self, source_id: &str) {
        if self.inner.closed.load(Ordering::Acquire) {
            return;
        }
        if let Some(source) = self.source(source_id) {
            source.start();
        }
    }

    pub(crate) async fn stop_source(&self, source_id: &str) {
        if let Some(source) = self.source(source_id) {
            source.stop().await;
        }
    }

    pub(crate) async fn remove_source(&self, source_id: &str) {
        let source = self
            .inner
            .sources
            .write()
            .unwrap_or_else(|error| error.into_inner())
            .remove(source_id);
        if let Some(source) = source {
            source.close().await;
        }
    }

    pub(crate) fn response(&self, source_id: &str) -> Option<Response> {
        self.source(source_id).map(|source| source.response())
    }

    pub(crate) fn viewer_count(&self, source_id: &str) -> usize {
        self.source(source_id)
            .map_or(0, |source| source.viewer_count())
    }

    pub(crate) fn latest_drawn(&self, source_id: &str) -> Option<Arc<DrawnFrame>> {
        self.source(source_id)
            .and_then(|source| source.latest_drawn())
    }

    pub(crate) async fn shutdown(&self) {
        self.inner.closed.store(true, Ordering::Release);
        let sources: Vec<_> = self
            .inner
            .sources
            .read()
            .unwrap_or_else(|error| error.into_inner())
            .values()
            .cloned()
            .collect();
        futures_util::future::join_all(sources.iter().map(|source| source.close())).await;
    }

    fn source(&self, source_id: &str) -> Option<Arc<SourceStream>> {
        self.inner
            .sources
            .read()
            .unwrap_or_else(|error| error.into_inner())
            .get(source_id)
            .cloned()
    }
}

async fn produce(
    source: Arc<SourceStream>,
    mut frames: broadcast::Receiver<Arc<Bytes>>,
    mut status: watch::Receiver<SourceStatus>,
) {
    let initial_state = status.borrow().state;
    update_lifecycle(&source, initial_state).await;
    loop {
        tokio::select! {
            changed = status.changed() => {
                if changed.is_err() {
                    break;
                }
                let next_state = status.borrow().state;
                update_lifecycle(&source, next_state).await;
            }
            frame = frames.recv() => match frame {
                Ok(bytes) if source.active.load(Ordering::Acquire) => {
                    let current = status.borrow().clone();
                    if current.resolution.width > 0 && current.resolution.height > 0 {
                        source.slot.pending.lock().await.replace(PendingFrame {
                            bytes,
                            width: current.resolution.width,
                            height: current.resolution.height,
                            generation: source.generation.load(Ordering::Acquire),
                        });
                        source.slot.notify.notify_one();
                    }
                }
                Ok(_) | Err(broadcast::error::RecvError::Lagged(_)) => {}
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
        if source.slot.closed.load(Ordering::Acquire) {
            break;
        }
    }
    source.close().await;
}

async fn update_lifecycle(source: &SourceStream, state: SourceState) {
    if matches!(
        state,
        SourceState::Connecting | SourceState::Active | SourceState::Reconnecting
    ) {
        source.start();
    } else {
        source.stop().await;
    }
}

async fn consume(
    source_id: String,
    source: Arc<SourceStream>,
    detector: DetectPipeline,
    semaphore: Arc<Semaphore>,
    encoder: Arc<dyn Encoder>,
    clock: Arc<dyn Clock>,
) {
    let mut next_encode = Duration::ZERO;
    loop {
        while source.slot.pending.lock().await.is_none() {
            if source.slot.closed.load(Ordering::Acquire) {
                return;
            }
            source.slot.notify.notified().await;
        }
        if clock.now() < next_encode {
            tokio::select! {
                () = clock.sleep_until(next_encode) => {}
                () = source.slot.notify.notified() => continue,
            }
        }
        let Some(pending) = source.slot.pending.lock().await.take() else {
            continue;
        };
        if !current(&source, pending.generation) {
            continue;
        }
        let Ok(permit) = Arc::clone(&semaphore).acquire_owned().await else {
            return;
        };
        if !current(&source, pending.generation) {
            drop(permit);
            continue;
        }
        next_encode = clock.now().saturating_add(FRAME_INTERVAL);
        let detections = detector.draw_result(&source_id).await;
        let task_encoder = Arc::clone(&encoder);
        let encoded = tokio::task::spawn_blocking(move || {
            let _permit = permit;
            let mut bytes = pending.bytes.to_vec();
            draw_detections(&mut bytes, pending.width, pending.height, &detections)?;
            let drawn = Arc::new(DrawnFrame {
                width: pending.width,
                height: pending.height,
                bytes: Bytes::from(bytes),
            });
            let jpeg = task_encoder.encode(&drawn, JPEG_QUALITY)?;
            Ok::<_, String>((drawn, jpeg, pending.generation))
        })
        .await;
        match encoded {
            Ok(Ok((drawn, jpeg, generation))) => source.publish(generation, drawn, jpeg),
            Ok(Err(error)) => tracing::warn!(%error, %source_id, "failed to encode MJPEG frame"),
            Err(error) => tracing::warn!(%error, %source_id, "MJPEG encode task failed"),
        }
    }
}

fn current(source: &SourceStream, generation: u64) -> bool {
    source.active.load(Ordering::Acquire) && source.generation.load(Ordering::Acquire) == generation
}

fn multipart_part(jpeg: &Bytes) -> Bytes {
    let header = format!(
        "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {}\r\n\r\n",
        jpeg.len()
    );
    let mut part = BytesMut::with_capacity(header.len() + jpeg.len() + 2);
    part.extend_from_slice(header.as_bytes());
    part.extend_from_slice(jpeg);
    part.extend_from_slice(b"\r\n");
    part.freeze()
}

#[cfg(test)]
mod tests {
    use std::sync::{Condvar, MutexGuard};

    use futures_util::StreamExt;
    use serde_json::json;
    use tokio::{sync::Barrier, time::timeout};

    use super::super::{detect::tests as detect_tests, run_bounded_paused_test, run_bounded_test};
    use super::*;

    /// Same reasoning as detect.rs: a watchdog against a hung test, not a
    /// budget for a slow one.
    const TEST_TIMEOUT: Duration = Duration::from_secs(60);
    const WIDTH: u32 = 32;
    const HEIGHT: u32 = 24;

    #[derive(Default)]
    struct FakeClock {
        nanos: AtomicU64,
    }

    impl Clock for FakeClock {
        fn now(&self) -> Duration {
            Duration::from_nanos(self.nanos.load(Ordering::Acquire))
        }

        fn sleep_until(&self, deadline: Duration) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
            Box::pin(async move {
                tokio::task::yield_now().await;
                self.nanos
                    .fetch_max(deadline.as_nanos() as u64, Ordering::AcqRel);
            })
        }
    }

    #[derive(Default)]
    struct FakeEncoder {
        calls: AtomicUsize,
        active: AtomicUsize,
        max_active: AtomicUsize,
        qualities: Mutex<Vec<u8>>,
        first_bytes: Mutex<Vec<u8>>,
        boxed: Mutex<Vec<bool>>,
        blocked: Mutex<bool>,
        wake: Condvar,
    }

    struct ActiveGuard<'a>(&'a AtomicUsize);

    impl Drop for ActiveGuard<'_> {
        fn drop(&mut self) {
            self.0.fetch_sub(1, Ordering::AcqRel);
        }
    }

    impl FakeEncoder {
        fn block(&self) {
            *self.blocked.lock().unwrap() = true;
        }

        fn release(&self) {
            *self.blocked.lock().unwrap() = false;
            self.wake.notify_all();
        }

        fn wait_if_blocked<'a>(&self, mut blocked: MutexGuard<'a, bool>) -> Result<(), String> {
            while *blocked {
                let (next, deadline) = self
                    .wake
                    .wait_timeout(blocked, Duration::from_secs(2))
                    .unwrap();
                blocked = next;
                if deadline.timed_out() {
                    return Err("fake encoder gate timed out".to_string());
                }
            }
            Ok(())
        }
    }

    impl Encoder for FakeEncoder {
        fn encode(&self, frame: &DrawnFrame, quality: u8) -> Result<Bytes, String> {
            self.calls.fetch_add(1, Ordering::AcqRel);
            let active = self.active.fetch_add(1, Ordering::AcqRel) + 1;
            let _guard = ActiveGuard(&self.active);
            self.max_active.fetch_max(active, Ordering::AcqRel);
            self.qualities.lock().unwrap().push(quality);
            self.first_bytes
                .lock()
                .unwrap()
                .push(frame.bytes.first().copied().unwrap_or_default());
            let boxed = frame.bytes.as_chunks::<3>().0.contains(&[0, 255, 0]);
            self.boxed.lock().unwrap().push(boxed);
            self.wait_if_blocked(self.blocked.lock().unwrap())?;
            Ok(Bytes::from_static(if boxed {
                b"\xff\xd8\x01\xff\xd9"
            } else {
                b"\xff\xd8\x00\xff\xd9"
            }))
        }
    }

    fn status(id: &str) -> SourceStatus {
        SourceStatus {
            id: id.to_string(),
            name: id.to_string(),
            url: "synthetic".to_string(),
            source_type: "file".to_string(),
            state: SourceState::Active,
            resolution: super::super::source_task::Resolution {
                width: WIDTH,
                height: HEIGHT,
            },
            fps: 0.0,
            frame_count: 0,
            error: String::new(),
        }
    }

    fn detector() -> DetectPipeline {
        DetectPipeline::new(
            None,
            Arc::new(json!({})),
            super::super::rules::RuleTask::spawn(Vec::new()),
        )
    }

    fn attach(
        hub: &MjpegHub,
        id: &str,
        detector: DetectPipeline,
    ) -> (
        Arc<SourceStream>,
        broadcast::Sender<Arc<Bytes>>,
        watch::Sender<SourceStatus>,
    ) {
        let (frames_tx, frames_rx) = broadcast::channel(16);
        let (status_tx, status_rx) = watch::channel(status(id));
        let source = hub.attach_receivers(id.to_string(), frames_rx, status_rx, detector);
        (source, frames_tx, status_tx)
    }

    fn frame(marker: u8) -> Arc<Bytes> {
        Arc::new(Bytes::from(vec![
            marker;
            WIDTH as usize * HEIGHT as usize * 3
        ]))
    }

    async fn wait_for(counter: &AtomicUsize, expected: usize) {
        timeout(Duration::from_secs(5), async {
            while counter.load(Ordering::Acquire) < expected {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("counter did not reach {expected}"));
    }

    /// Wait until a recorded vector reaches `expected` entries.
    ///
    /// `wait_for(&encoder.calls, n)` is NOT a substitute: `FakeEncoder::encode`
    /// bumps `calls` on entry and pushes to the vectors several lines later, so
    /// the counter reaching `n` only means the nth encode *started*. Asserting
    /// on `first_bytes` right after such a wait saw `[1, 2]` where `[1, 2, 4]`
    /// was expected, but only under load -- which is what made it look flaky.
    async fn wait_for_len<T>(recorded: &Mutex<Vec<T>>, expected: usize) {
        timeout(Duration::from_secs(5), async {
            while recorded.lock().unwrap().len() < expected {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("recorded vector did not reach {expected} entries"));
    }

    async fn wait_for_named(counter: &AtomicUsize, expected: usize, label: &str) {
        timeout(Duration::from_secs(5), async {
            while counter.load(Ordering::Acquire) < expected {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("{label} did not reach {expected}"));
    }

    async fn wait_active(source: &SourceStream) {
        timeout(Duration::from_secs(1), async {
            while !source.active.load(Ordering::Acquire) {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("MJPEG source did not become active");
    }

    #[test]
    fn quality_rate_single_encode_latest_pending_and_global_two_are_fixed() {
        run_bounded_test(TEST_TIMEOUT, async {
            let encoder = Arc::new(FakeEncoder::default());
            let clock = Arc::new(FakeClock::default());
            let hub = MjpegHub::with_components(encoder.clone(), clock.clone());
            let (source, frames, _status) = attach(&hub, "cam", detector());
            wait_active(&source).await;
            let mut first_viewer = source.body().into_data_stream();
            let mut second_viewer = source.body().into_data_stream();

            frames.send(frame(1)).unwrap();
            wait_for(&encoder.calls, 1).await;
            let first = timeout(Duration::from_secs(1), first_viewer.next())
                .await
                .unwrap()
                .unwrap()
                .unwrap();
            let second = timeout(Duration::from_secs(1), second_viewer.next())
                .await
                .unwrap()
                .unwrap()
                .unwrap();
            assert_eq!(first, second);
            assert_eq!(encoder.calls.load(Ordering::Acquire), 1);
            assert_eq!(
                encoder.qualities.lock().unwrap().as_slice(),
                &[JPEG_QUALITY]
            );

            encoder.block();
            frames.send(frame(2)).unwrap();
            wait_for(&encoder.calls, 2).await;
            frames.send(frame(3)).unwrap();
            frames.send(frame(4)).unwrap();
            encoder.release();
            // Wait for the third encode to have RECORDED its frame, not merely
            // to have started: `calls` is bumped on entry and `first_bytes` is
            // pushed a few lines later, so waiting on the counter here read
            // `[1, 2]` under load.
            wait_for_len(&encoder.first_bytes, 3).await;
            assert_eq!(encoder.first_bytes.lock().unwrap().as_slice(), &[1, 2, 4]);
            assert!(clock.now() >= FRAME_INTERVAL.saturating_mul(2));
            assert!(encoder
                .qualities
                .lock()
                .unwrap()
                .iter()
                .all(|quality| *quality == JPEG_QUALITY));

            let encoder = Arc::new(FakeEncoder::default());
            encoder.block();
            let hub = MjpegHub::with_components(encoder.clone(), Arc::new(FakeClock::default()));
            let (_, one, _one_status) = attach(&hub, "one", detector());
            let (two_source, two, _two_status) = attach(&hub, "two", detector());
            let (three_source, three, _three_status) = attach(&hub, "three", detector());
            wait_active(&hub.source("one").unwrap()).await;
            wait_active(&two_source).await;
            wait_active(&three_source).await;
            one.send(frame(1)).unwrap();
            two.send(frame(2)).unwrap();
            three.send(frame(3)).unwrap();
            // Wait on `active`, not `calls`: `max_active` is updated after the
            // `calls` bump, so waiting on the counter could read a stale peak.
            // The encoders are blocked, so once `active` reaches the cap it
            // stays there -- and asserting `max_active` afterwards still tests
            // what it is meant to (that the cap was never exceeded).
            wait_for(&encoder.active, ENCODE_CONCURRENCY).await;
            assert_eq!(
                encoder.max_active.load(Ordering::Acquire),
                ENCODE_CONCURRENCY
            );
            assert_eq!(encoder.calls.load(Ordering::Acquire), ENCODE_CONCURRENCY);
            encoder.release();
            wait_for(&encoder.calls, 3).await;
            assert_eq!(
                encoder.max_active.load(Ordering::Acquire),
                ENCODE_CONCURRENCY
            );
            hub.shutdown().await;
        });
    }

    #[test]
    fn metadata_and_detect_backoff_keep_plain_mjpeg_then_restore_boxes() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let stub_state = detect_tests::StubState::default();
            stub_state
                .metadata_delays
                .lock()
                .await
                .push_back(Duration::from_millis(700));
            stub_state
                .detect_delays
                .lock()
                .await
                .push_back(Duration::from_millis(700));
            let (client, server) = detect_tests::stub(stub_state.clone()).await;
            let detector = detect_tests::pipeline_with_backoff(
                client,
                json!({}),
                Duration::from_millis(300),
                Duration::from_secs(1),
            );
            let (handle, status_tx) = detect_tests::source("cam", WIDTH, HEIGHT);
            detector.attach("cam".to_string(), &handle);
            let encoder = Arc::new(FakeEncoder::default());
            let hub = MjpegHub::with_components(encoder.clone(), Arc::new(FakeClock::default()));
            hub.attach("cam".to_string(), &handle, detector.clone());
            wait_active(&hub.source("cam").unwrap()).await;
            timeout(Duration::from_secs(1), async {
                while detector.snapshot().await.skip_rate != 0 {
                    tokio::task::yield_now().await;
                }
            })
            .await
            .expect("detector source did not become active");
            let mut body = hub.response("cam").unwrap().into_body().into_data_stream();

            handle.frames_tx.send(frame(1)).unwrap();
            wait_for_named(&stub_state.metadata_calls, 1, "metadata calls").await;
            assert!(body.next().await.unwrap().is_ok());
            tokio::time::advance(Duration::from_millis(300)).await;
            detect_tests::wait_for_error(&handle, "metadata timed out").await;

            handle.frames_tx.send(frame(2)).unwrap();
            assert!(body.next().await.unwrap().is_ok());
            tokio::time::advance(Duration::from_secs(1)).await;
            wait_for_named(
                &stub_state.metadata_calls,
                2,
                "metadata calls after recovery",
            )
            .await;
            wait_for_named(
                &stub_state.detect_calls,
                1,
                "detect calls after metadata recovery",
            )
            .await;
            tokio::time::advance(Duration::from_millis(300)).await;
            detect_tests::wait_for_error(&handle, "detection timed out").await;

            handle.frames_tx.send(frame(3)).unwrap();
            assert!(body.next().await.unwrap().is_ok());
            tokio::time::advance(Duration::from_secs(1)).await;
            wait_for_named(
                &stub_state.detect_calls,
                2,
                "detect calls after detect recovery",
            )
            .await;
            detect_tests::wait_for_result(&detector, "cam", "MJPEG recovery").await;
            handle.frames_tx.send(frame(4)).unwrap();
            assert!(body.next().await.unwrap().is_ok());

            let boxed = encoder.boxed.lock().unwrap().clone();
            assert!(boxed.len() >= 4);
            assert!(boxed[..3].iter().all(|value| !value));
            assert!(boxed[3]);
            assert!(hub.latest_drawn("cam").is_some());
            assert!(detector
                .drawn_frame("cam")
                .await
                .unwrap()
                .bytes
                .as_chunks::<3>()
                .0
                .contains(&[0, 255, 0]));
            assert!(!status_tx.is_closed());
            hub.shutdown().await;
            server.abort();
        });
    }

    #[test]
    fn five_competing_viewers_cap_at_four_and_drop_or_cancel_returns_counter() {
        run_bounded_test(TEST_TIMEOUT, async {
            let hub = MjpegHub::with_components(
                Arc::new(FakeEncoder::default()),
                Arc::new(FakeClock::default()),
            );
            let (source, _frames, _status) = attach(&hub, "cam", detector());
            wait_active(&source).await;
            let barrier = Arc::new(Barrier::new(6));
            let mut tasks = Vec::new();
            for _ in 0..5 {
                let barrier = Arc::clone(&barrier);
                let source = Arc::clone(&source);
                tasks.push(tokio::spawn(async move {
                    barrier.wait().await;
                    source.response()
                }));
            }
            barrier.wait().await;
            let responses = futures_util::future::join_all(tasks)
                .await
                .into_iter()
                .map(Result::unwrap)
                .collect::<Vec<_>>();
            assert!(responses
                .iter()
                .all(|response| response.status().as_u16() == 200));
            assert!(responses
                .iter()
                .all(|response| response.headers()[header::CONTENT_TYPE] == CONTENT_TYPE));
            assert_eq!(source.viewer_count(), MAX_VIEWERS);

            let jpeg = Bytes::from_static(b"jpeg");
            source.publish(
                source.generation.load(Ordering::Acquire),
                Arc::new(DrawnFrame {
                    width: 1,
                    height: 1,
                    bytes: Bytes::from_static(&[0, 0, 0]),
                }),
                jpeg,
            );
            let mut streams = responses
                .into_iter()
                .map(|response| response.into_body().into_data_stream())
                .collect::<Vec<_>>();
            let mut data = 0;
            let mut eof = 0;
            for stream in &mut streams {
                match timeout(Duration::from_secs(1), stream.next())
                    .await
                    .unwrap()
                {
                    Some(Ok(_)) => data += 1,
                    None => eof += 1,
                    Some(Err(error)) => panic!("viewer body failed: {error}"),
                }
            }
            assert_eq!((data, eof), (MAX_VIEWERS, 1));
            drop(streams);
            assert_eq!(source.viewer_count(), 0);

            let body = source.body();
            assert_eq!(source.viewer_count(), 1);
            let request = tokio::spawn(async move {
                let _body = body;
                std::future::pending::<()>().await;
            });
            request.abort();
            let _ = request.await;
            assert_eq!(source.viewer_count(), 0);
        });
    }

    #[test]
    fn stop_during_encode_discards_old_result_and_closes_existing_and_new_bodies() {
        run_bounded_test(TEST_TIMEOUT, async {
            let encoder = Arc::new(FakeEncoder::default());
            encoder.block();
            let hub = MjpegHub::with_components(encoder.clone(), Arc::new(FakeClock::default()));
            let (source, frames, _status) = attach(&hub, "cam", detector());
            wait_active(&source).await;
            let mut existing = source.body().into_data_stream();
            frames.send(frame(1)).unwrap();
            wait_for(&encoder.calls, 1).await;
            source.stop().await;
            encoder.release();

            assert!(timeout(Duration::from_secs(1), existing.next())
                .await
                .unwrap()
                .is_none());
            let mut fresh = source.body().into_data_stream();
            assert!(timeout(Duration::from_secs(1), fresh.next())
                .await
                .unwrap()
                .is_none());
            assert!(source.latest_drawn().is_none());
        });
    }

    #[test]
    fn shutdown_closes_every_body_within_deadline() {
        run_bounded_test(TEST_TIMEOUT, async {
            let hub = MjpegHub::with_components(
                Arc::new(FakeEncoder::default()),
                Arc::new(FakeClock::default()),
            );
            let (one, _one_frames, _one_status) = attach(&hub, "one", detector());
            let (two, _two_frames, _two_status) = attach(&hub, "two", detector());
            wait_active(&one).await;
            wait_active(&two).await;
            let mut first = one.body().into_data_stream();
            let mut second = two.body().into_data_stream();
            hub.shutdown().await;
            assert!(timeout(Duration::from_secs(1), first.next())
                .await
                .unwrap()
                .is_none());
            assert!(timeout(Duration::from_secs(1), second.next())
                .await
                .unwrap()
                .is_none());
            assert_eq!(one.viewer_count(), 0);
            assert_eq!(two.viewer_count(), 0);
        });
    }

    #[test]
    fn lagged_viewer_resumes_and_first_part_is_byte_exact() {
        run_bounded_test(TEST_TIMEOUT, async {
            let source = SourceStream::new();
            source.start();
            let mut body = source.body().into_data_stream();
            let generation = source.generation.load(Ordering::Acquire);
            let drawn = Arc::new(DrawnFrame {
                width: 1,
                height: 1,
                bytes: Bytes::from_static(&[0, 0, 0]),
            });
            source.publish(generation, Arc::clone(&drawn), Bytes::from_static(b"one"));
            source.publish(generation, Arc::clone(&drawn), Bytes::from_static(b"two"));
            source.publish(generation, drawn, Bytes::from_static(b"three"));

            let part = timeout(Duration::from_secs(1), body.next())
                .await
                .unwrap()
                .unwrap()
                .unwrap();
            assert_eq!(
                part,
                Bytes::from_static(
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 3\r\n\r\ntwo\r\n"
                )
            );
            source.stop().await;
        });
    }
}
