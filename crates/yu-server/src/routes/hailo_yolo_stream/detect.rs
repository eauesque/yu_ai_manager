use std::{
    collections::{BTreeMap, VecDeque},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, Instant, SystemTime},
};

use base64::{engine::general_purpose::STANDARD, Engine};
use bytes::Bytes;
use chrono::Local;
use infer_core::yolo_postprocess::Detection;
use serde_json::Value;
use tokio::sync::{broadcast, Mutex, Notify};

use super::{
    draw::{drawn_frame, DrawnFrame},
    rules::{RuleHandle, TriggerFrame},
    source_task::{SourceHandle, SourceState},
};
use crate::{
    infer_client::InferClient,
    routes::{hailo_yolo_detect::hailo_yolo_hef_path, hailo_yolo_preprocess::letterbox_resize},
};

const INPUT_SIZE: u32 = 640;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(5);
const RETRY_BACKOFFS: [Duration; 6] = [
    Duration::from_secs(1),
    Duration::from_secs(2),
    Duration::from_secs(4),
    Duration::from_secs(8),
    Duration::from_secs(16),
    Duration::from_secs(30),
];
const FPS_WINDOW: usize = 30;

#[derive(Clone)]
pub(crate) struct DetectPipeline {
    inner: Arc<DetectInner>,
}

struct DetectInner {
    infer_client: Option<InferClient>,
    model_name: String,
    conf_threshold: f64,
    metadata: Mutex<Option<(HefKey, usize)>>,
    results: Mutex<BTreeMap<String, Arc<Vec<Detection>>>>,
    draw_results: Mutex<BTreeMap<String, Arc<Vec<Detection>>>>,
    drawn_frames: Mutex<BTreeMap<String, Arc<DrawnFrame>>>,
    completions: Mutex<VecDeque<tokio::time::Instant>>,
    active_sources: AtomicUsize,
    queue_size: AtomicUsize,
    rules: RuleHandle,
    rule_started_at: Instant,
    timing: Timing,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct HefKey {
    model_name: String,
    path: Option<PathBuf>,
    size: Option<u64>,
    modified: Option<SystemTime>,
}

#[derive(Clone, Copy)]
struct Timing {
    request_timeout: Duration,
    retry_backoffs: [Duration; 6],
}

struct LatestSlot {
    frame: Mutex<Option<FrameInput>>,
    notify: Notify,
    closed: AtomicBool,
    active: AtomicBool,
}

#[derive(Clone)]
struct FrameInput {
    bytes: Arc<Bytes>,
    width: u32,
    height: u32,
}

pub(crate) struct DetectSnapshot {
    pub(crate) queue_size: usize,
    pub(crate) skip_rate: usize,
    pub(crate) fps: f64,
    pub(crate) model_name: String,
    pub(crate) conf_threshold: f64,
    pub(crate) result_sources: Vec<String>,
}

impl DetectPipeline {
    pub(crate) fn new(
        infer_client: Option<InferClient>,
        settings: Arc<Value>,
        rules: RuleHandle,
    ) -> Self {
        Self::with_timing(
            infer_client,
            settings,
            rules,
            Timing {
                request_timeout: REQUEST_TIMEOUT,
                retry_backoffs: RETRY_BACKOFFS,
            },
        )
    }

    fn with_timing(
        infer_client: Option<InferClient>,
        settings: Arc<Value>,
        rules: RuleHandle,
        timing: Timing,
    ) -> Self {
        Self {
            inner: Arc::new(DetectInner {
                infer_client,
                model_name: settings
                    .get("model")
                    .and_then(Value::as_str)
                    .unwrap_or("yolov8n")
                    .to_string(),
                conf_threshold: settings
                    .get("confidence_threshold")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.25),
                metadata: Mutex::new(None),
                results: Mutex::new(BTreeMap::new()),
                draw_results: Mutex::new(BTreeMap::new()),
                drawn_frames: Mutex::new(BTreeMap::new()),
                completions: Mutex::new(VecDeque::with_capacity(FPS_WINDOW)),
                active_sources: AtomicUsize::new(0),
                queue_size: AtomicUsize::new(0),
                rules,
                rule_started_at: Instant::now(),
                timing,
            }),
        }
    }

    pub(crate) fn attach(&self, source_id: String, handle: &SourceHandle) {
        let slot = Arc::new(LatestSlot {
            frame: Mutex::new(None),
            notify: Notify::new(),
            closed: AtomicBool::new(false),
            active: AtomicBool::new(false),
        });
        let frames = handle.frames_tx.subscribe();
        let status = handle.status_rx.clone();
        let detection_error = handle.detection_error.clone();
        let producer_error = detection_error.clone();
        let producer = self.clone();
        let producer_slot = Arc::clone(&slot);
        let producer_id = source_id.clone();
        tokio::spawn(async move {
            producer
                .produce(producer_id, frames, status, producer_error, producer_slot)
                .await;
        });
        let consumer = self.clone();
        tokio::spawn(async move { consumer.consume(source_id, slot, detection_error).await });
    }

    pub(crate) async fn snapshot(&self) -> DetectSnapshot {
        let completions = self.inner.completions.lock().await;
        let fps = completion_fps(&completions);
        drop(completions);
        DetectSnapshot {
            queue_size: self.inner.queue_size.load(Ordering::Acquire),
            skip_rate: skip_rate(self.inner.active_sources.load(Ordering::Acquire)),
            fps,
            model_name: self.inner.model_name.clone(),
            conf_threshold: self.inner.conf_threshold,
            result_sources: self.inner.results.lock().await.keys().cloned().collect(),
        }
    }

    pub(crate) async fn draw_result(&self, source_id: &str) -> Arc<Vec<Detection>> {
        self.inner
            .draw_results
            .lock()
            .await
            .get(source_id)
            .cloned()
            .unwrap_or_default()
    }

    pub(crate) async fn drawn_frame(&self, source_id: &str) -> Option<Arc<DrawnFrame>> {
        self.inner.drawn_frames.lock().await.get(source_id).cloned()
    }

    async fn produce(
        &self,
        source_id: String,
        mut frames: broadcast::Receiver<Arc<Bytes>>,
        mut status: tokio::sync::watch::Receiver<super::source_task::SourceStatus>,
        detection_error: tokio::sync::watch::Sender<Option<String>>,
        slot: Arc<LatestSlot>,
    ) {
        let mut active = false;
        let mut counter = 0usize;
        self.update_active(
            &slot,
            &mut active,
            status.borrow().state == SourceState::Active,
        );
        loop {
            tokio::select! {
                changed = status.changed() => {
                    if changed.is_err() {
                        break;
                    }
                    let next = status.borrow().state == SourceState::Active;
                    self.update_active(&slot, &mut active, next);
                    if !next {
                        self.clear_slot(&slot).await;
                        self.clear_result(&source_id).await;
                        self.clear_draw_result(&source_id).await;
                        self.clear_drawn_frame(&source_id).await;
                        detection_error.send_replace(None);
                    }
                }
                frame = frames.recv() => match frame {
                    Ok(bytes) if active => {
                        let rate = skip_rate(self.inner.active_sources.load(Ordering::Acquire));
                        let process = counter.is_multiple_of(rate + 1);
                        counter = counter.wrapping_add(1);
                        if process {
                            let (width, height) = {
                                let current = status.borrow();
                                (current.resolution.width, current.resolution.height)
                            };
                            self.enqueue(&slot, FrameInput {
                                bytes,
                                width,
                                height,
                            }).await;
                        }
                    }
                    Ok(_) | Err(broadcast::error::RecvError::Lagged(_)) => {}
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
        }
        self.update_active(&slot, &mut active, false);
        slot.closed.store(true, Ordering::Release);
        self.clear_slot(&slot).await;
        self.clear_result(&source_id).await;
        self.clear_draw_result(&source_id).await;
        self.clear_drawn_frame(&source_id).await;
        detection_error.send_replace(None);
        slot.notify.notify_waiters();
    }

    fn update_active(&self, slot: &LatestSlot, current: &mut bool, next: bool) {
        if *current == next {
            return;
        }
        if next {
            self.inner.active_sources.fetch_add(1, Ordering::AcqRel);
        } else {
            self.inner.active_sources.fetch_sub(1, Ordering::AcqRel);
        }
        slot.active.store(next, Ordering::Release);
        *current = next;
    }

    async fn enqueue(&self, slot: &LatestSlot, frame: FrameInput) {
        let mut pending = slot.frame.lock().await;
        if pending.replace(frame).is_none() {
            self.inner.queue_size.fetch_add(1, Ordering::AcqRel);
        }
        drop(pending);
        slot.notify.notify_one();
    }

    async fn clear_slot(&self, slot: &LatestSlot) {
        if slot.frame.lock().await.take().is_some() {
            self.inner.queue_size.fetch_sub(1, Ordering::AcqRel);
        }
    }

    async fn take(&self, slot: &LatestSlot) -> Option<FrameInput> {
        loop {
            if let Some(frame) = slot.frame.lock().await.take() {
                self.inner.queue_size.fetch_sub(1, Ordering::AcqRel);
                return Some(frame);
            }
            if slot.closed.load(Ordering::Acquire) {
                return None;
            }
            slot.notify.notified().await;
        }
    }

    async fn consume(
        &self,
        source_id: String,
        slot: Arc<LatestSlot>,
        detection_error: tokio::sync::watch::Sender<Option<String>>,
    ) {
        let mut failures = 0usize;
        let mut retry_at = tokio::time::Instant::now();
        while !slot.closed.load(Ordering::Acquire) {
            tokio::time::sleep_until(retry_at).await;
            let Some(frame) = self.take(&slot).await else {
                break;
            };
            self.clear_result(&source_id).await;
            let trigger = frame.clone();
            match self.detect(frame).await {
                Ok(detections) if slot.active.load(Ordering::Acquire) => {
                    detection_error.send_replace(None);
                    failures = 0;
                    retry_at = tokio::time::Instant::now();
                    drop(self.inner.rules.evaluate(
                        source_id.clone(),
                        &detections,
                        TriggerFrame {
                            bytes: (*trigger.bytes).clone(),
                            width: trigger.width,
                            height: trigger.height,
                        },
                        Local::now().naive_local(),
                        self.inner.rule_started_at.elapsed(),
                    ));
                    match drawn_frame(&trigger.bytes, trigger.width, trigger.height, &detections) {
                        Ok(frame) => {
                            self.inner
                                .drawn_frames
                                .lock()
                                .await
                                .insert(source_id.clone(), Arc::new(frame));
                        }
                        Err(error) => {
                            self.clear_drawn_frame(&source_id).await;
                            reporter_error(&source_id, &error);
                        }
                    }
                    self.inner
                        .results
                        .lock()
                        .await
                        .insert(source_id.clone(), Arc::new(detections.clone()));
                    self.inner
                        .draw_results
                        .lock()
                        .await
                        .insert(source_id.clone(), Arc::new(detections));
                    let mut completions = self.inner.completions.lock().await;
                    if completions.len() == FPS_WINDOW {
                        completions.pop_front();
                    }
                    completions.push_back(tokio::time::Instant::now());
                }
                Ok(_) => {}
                Err(error) => {
                    self.clear_draw_result(&source_id).await;
                    self.clear_drawn_frame(&source_id).await;
                    detection_error.send_replace(Some(error.clone()));
                    reporter_error(&source_id, &error);
                    failures = failures.saturating_add(1);
                    retry_at = tokio::time::Instant::now()
                        + self.inner.timing.retry_backoffs
                            [failures.saturating_sub(1).min(RETRY_BACKOFFS.len() - 1)];
                }
            }
        }
    }

    async fn clear_result(&self, source_id: &str) {
        self.inner.results.lock().await.remove(source_id);
    }

    async fn clear_draw_result(&self, source_id: &str) {
        self.inner.draw_results.lock().await.remove(source_id);
    }

    async fn clear_drawn_frame(&self, source_id: &str) {
        self.inner.drawn_frames.lock().await.remove(source_id);
    }

    async fn detect(&self, frame: FrameInput) -> Result<Vec<Detection>, String> {
        let client = self
            .inner
            .infer_client
            .as_ref()
            .ok_or_else(|| "Hailo inference unavailable".to_string())?;
        let hef_path = hailo_yolo_hef_path(&self.inner.model_name);
        let frame_size = self.frame_size(client, hef_path.clone()).await?;
        let expected = frame
            .width
            .checked_mul(frame.height)
            .and_then(|pixels| pixels.checked_mul(3))
            .and_then(|bytes| usize::try_from(bytes).ok())
            .ok_or_else(|| "source frame dimensions overflow".to_string())?;
        if frame.bytes.len() != expected {
            return Err(format!(
                "source frame size mismatch: expected {expected}, got {}",
                frame.bytes.len()
            ));
        }
        let mut rgb = frame.bytes.to_vec();
        for pixel in rgb.as_chunks_mut::<3>().0 {
            pixel.swap(0, 2);
        }
        let image = image::RgbImage::from_raw(frame.width, frame.height, rgb)
            .map(image::DynamicImage::ImageRgb8)
            .ok_or_else(|| "source frame dimensions are invalid".to_string())?;
        let (input, scale) = letterbox_resize(&image, INPUT_SIZE);
        if input.len() != frame_size {
            return Err(format!(
                "HEF input size mismatch: expected {frame_size}, got {}",
                input.len()
            ));
        }
        tokio::time::timeout(
            self.inner.timing.request_timeout,
            client.infer_yolo_detect(
                hef_path,
                STANDARD.encode(input),
                self.inner.conf_threshold,
                0.45,
                80,
                INPUT_SIZE,
                scale.orig_w,
                scale.orig_h,
                scale.scale,
                scale.pad_x,
                scale.pad_y,
            ),
        )
        .await
        .map_err(|_| "Hailo detection timed out".to_string())?
        .map_err(|error| error.to_string())
    }

    async fn frame_size(
        &self,
        client: &InferClient,
        hef_path: Option<String>,
    ) -> Result<usize, String> {
        let key = hef_key(&self.inner.model_name, hef_path.as_deref()).await;
        let mut cached = self.inner.metadata.lock().await;
        if let Some(frame_size) = cached_frame_size(&cached, &key) {
            return Ok(frame_size);
        }
        *cached = None;
        let metadata = tokio::time::timeout(
            self.inner.timing.request_timeout,
            client.infer_yolo_metadata(hef_path),
        )
        .await
        .map_err(|_| "Hailo metadata timed out".to_string())?
        .map_err(|error| error.to_string())?;
        let frame_size = metadata
            .pointer("/inputs/0/frame_size")
            .and_then(Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .ok_or_else(|| "Hailo metadata is missing inputs[0].frame_size".to_string())?;
        *cached = Some((key, frame_size));
        Ok(frame_size)
    }
}

fn cached_frame_size(cached: &Option<(HefKey, usize)>, key: &HefKey) -> Option<usize> {
    cached
        .as_ref()
        .filter(|(cached_key, _)| cached_key == key)
        .map(|(_, frame_size)| *frame_size)
}

async fn hef_key(model_name: &str, hef_path: Option<&str>) -> HefKey {
    let path = hef_path.map(PathBuf::from).or_else(|| {
        std::env::var_os("HAILO_YOLO_HEF")
            .map(PathBuf::from)
            .or_else(|| {
                crate::routes::hailo_model_download::YOLO_MODELS
                    .get(model_name)
                    .map(|info| {
                        crate::routes::hailo_model_download::default_hef_dir()
                            .join(&info.hef_filename)
                    })
            })
    });
    let (path, size, modified) = match path {
        Some(path) => match tokio::fs::metadata(&path).await {
            Ok(metadata) => (
                tokio::fs::canonicalize(&path).await.ok().or(Some(path)),
                Some(metadata.len()),
                metadata.modified().ok(),
            ),
            Err(_) => (Some(path), None, None),
        },
        None => (None, None, None),
    };
    HefKey {
        model_name: model_name.to_string(),
        path,
        size,
        modified,
    }
}

fn skip_rate(source_count: usize) -> usize {
    match source_count {
        1 => 0,
        2 => 1,
        3 => 2,
        _ => 3,
    }
}

fn completion_fps(completions: &VecDeque<tokio::time::Instant>) -> f64 {
    let (Some(first), Some(last)) = (completions.front(), completions.back()) else {
        return 0.0;
    };
    let elapsed = last.duration_since(*first).as_secs_f64();
    if completions.len() < 2 || elapsed <= 0.0 {
        0.0
    } else {
        (((completions.len() - 1) as f64 / elapsed) * 10.0).round() / 10.0
    }
}

fn reporter_error(source_id: &str, error: &str) {
    tracing::warn!(source_id, error, "Hailo stream detection degraded");
}

#[cfg(test)]
pub(super) mod tests {
    use std::{
        collections::VecDeque,
        process::Command,
        sync::atomic::{AtomicUsize, Ordering},
    };

    use axum::{
        extract::State,
        routing::{get, post},
        Json, Router,
    };
    use serde_json::json;
    use tokio::{net::TcpListener, sync::watch, task::JoinHandle};

    use super::super::{
        run_bounded_paused_test, run_bounded_test,
        source_task::{Resolution, SourceCommand, SourceStatus},
    };
    use super::*;

    /// Watchdog for a hung test, not a budget for a slow one. These tests run
    /// ~4s idle and ~6.5s under moderate CPU load (measured 2026-08-29), and a
    /// full-suite run alongside continuous cargo builds pushed
    /// source_count_policy_skips_real_requests_and_status_is_stable to 15s --
    /// the deadline fired on a healthy run. A genuinely hung test never
    /// finishes, so a wide budget still catches it while a tight one only
    /// manufactures flakes.
    const TEST_TIMEOUT: Duration = Duration::from_secs(60);
    const FRAME_SIZE: usize = INPUT_SIZE as usize * INPUT_SIZE as usize * 3;

    #[derive(Clone, Default)]
    pub(crate) struct StubState {
        pub(crate) metadata_calls: Arc<AtomicUsize>,
        pub(crate) detect_calls: Arc<AtomicUsize>,
        detect_in_flight: Arc<AtomicUsize>,
        max_detect_in_flight: Arc<AtomicUsize>,
        pub(crate) metadata_delays: Arc<Mutex<VecDeque<Duration>>>,
        pub(crate) detect_delays: Arc<Mutex<VecDeque<Duration>>>,
        requests: Arc<Mutex<Vec<Value>>>,
    }

    struct InFlightGuard(StubState);

    impl Drop for InFlightGuard {
        fn drop(&mut self) {
            self.0.detect_in_flight.fetch_sub(1, Ordering::AcqRel);
        }
    }

    impl StubState {
        async fn metadata(State(state): State<Self>) -> Json<Value> {
            state.metadata_calls.fetch_add(1, Ordering::AcqRel);
            delay(&state.metadata_delays).await;
            Json(json!({"inputs": [{"frame_size": FRAME_SIZE}]}))
        }

        async fn detect(State(state): State<Self>, Json(body): Json<Value>) -> Json<Value> {
            state.detect_calls.fetch_add(1, Ordering::AcqRel);
            let current = state.detect_in_flight.fetch_add(1, Ordering::AcqRel) + 1;
            state
                .max_detect_in_flight
                .fetch_max(current, Ordering::AcqRel);
            let _guard = InFlightGuard(state.clone());
            state.requests.lock().await.push(body);
            delay(&state.detect_delays).await;
            Json(json!({"data": {"detections": [{
                "class_id": 0,
                "class_name": "person",
                "confidence": 0.75,
                "bbox": [0.1, 0.1, 0.8, 0.8]
            }]}}))
        }
    }

    async fn delay(delays: &Mutex<VecDeque<Duration>>) {
        let delay = delays.lock().await.pop_front();
        if let Some(delay) = delay {
            tokio::time::sleep(delay).await;
        }
    }

    pub(crate) async fn stub(state: StubState) -> (InferClient, JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/v1/infer/yolo/metadata", get(StubState::metadata))
            .route("/v1/infer/yolo/detect", post(StubState::detect))
            .with_state(state);
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (
            InferClient::new(format!("http://{address}"), "test".to_string()),
            server,
        )
    }

    pub(crate) fn source(
        id: &str,
        width: u32,
        height: u32,
    ) -> (SourceHandle, watch::Sender<SourceStatus>) {
        let (cmd_tx, _) = tokio::sync::mpsc::channel::<SourceCommand>(1);
        let (status_tx, status_rx) = watch::channel(SourceStatus {
            id: id.to_string(),
            name: id.to_string(),
            url: "synthetic".to_string(),
            source_type: "file".to_string(),
            state: SourceState::Active,
            resolution: Resolution { width, height },
            fps: 0.0,
            frame_count: 0,
            error: String::new(),
        });
        let (frames_tx, _) = broadcast::channel(16);
        let (detection_error, _) = watch::channel(None);
        (
            SourceHandle {
                cmd_tx,
                status_rx,
                frames_tx,
                detection_error,
            },
            status_tx,
        )
    }

    pub(crate) fn pipeline(
        client: InferClient,
        settings: Value,
        timeout: Duration,
    ) -> DetectPipeline {
        pipeline_with_backoff(client, settings, timeout, Duration::from_millis(20))
    }

    pub(crate) fn pipeline_with_backoff(
        client: InferClient,
        settings: Value,
        timeout: Duration,
        backoff: Duration,
    ) -> DetectPipeline {
        DetectPipeline::with_timing(
            Some(client),
            Arc::new(settings),
            super::super::rules::RuleTask::spawn(Vec::new()),
            Timing {
                request_timeout: timeout,
                retry_backoffs: [backoff; 6],
            },
        )
    }

    pub(crate) fn red_bgr(width: u32, height: u32) -> Arc<Bytes> {
        let mut bytes = vec![0; width as usize * height as usize * 3];
        for pixel in bytes.as_chunks_mut::<3>().0 {
            pixel[2] = 255;
        }
        Arc::new(Bytes::from(bytes))
    }

    fn blue_bgr(width: u32, height: u32) -> Arc<Bytes> {
        let mut bytes = vec![0; width as usize * height as usize * 3];
        for pixel in bytes.as_chunks_mut::<3>().0 {
            pixel[0] = 255;
        }
        Arc::new(Bytes::from(bytes))
    }

    pub(crate) async fn wait_for(counter: &AtomicUsize, expected: usize) {
        tokio::time::timeout(Duration::from_secs(5), async {
            while counter.load(Ordering::Acquire) < expected {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("counter did not reach the expected value");
    }

    pub(crate) async fn wait_for_result(pipeline: &DetectPipeline, source_id: &str, label: &str) {
        tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                if pipeline
                    .snapshot()
                    .await
                    .result_sources
                    .iter()
                    .any(|id| id == source_id)
                {
                    return;
                }
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap_or_else(|_| panic!("result was not published: {label}"));
    }

    pub(crate) async fn wait_for_error(handle: &SourceHandle, message: &str) {
        let mut errors = handle.detection_error.subscribe();
        tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                if errors
                    .borrow()
                    .as_deref()
                    .is_some_and(|error| error.contains(message))
                {
                    return;
                }
                errors
                    .changed()
                    .await
                    .expect("detection error channel closed");
            }
        })
        .await
        .unwrap_or_else(|_| panic!("source error did not contain {message}"));
    }

    #[test]
    fn request_reuses_letterbox_rgb_geometry_model_confidence_and_metadata_cache() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = StubState::default();
            let (client, server) = stub(state.clone()).await;
            let pipeline = pipeline(
                client,
                json!({"model": "yolov11n", "confidence_threshold": 0.37}),
                Duration::from_secs(1),
            );
            let (source, _status) = source("cam", INPUT_SIZE, INPUT_SIZE);
            pipeline.attach("cam".to_string(), &source);
            source
                .frames_tx
                .send(red_bgr(INPUT_SIZE, INPUT_SIZE))
                .unwrap();
            wait_for_result(&pipeline, "cam", "request contract").await;

            let requests = state.requests.lock().await;
            let body = requests.first().unwrap();
            let input = STANDARD
                .decode(body["input_base64"].as_str().unwrap())
                .unwrap();
            assert_eq!(input.len(), FRAME_SIZE);
            assert!(input.as_chunks::<3>().0.iter().all(|&p| p == [255, 0, 0]));
            assert_eq!(body["orig_w"], INPUT_SIZE);
            assert_eq!(body["orig_h"], INPUT_SIZE);
            assert_eq!(body["scale"], 1.0);
            assert_eq!(body["pad_x"], 0.0);
            assert_eq!(body["pad_y"], 0.0);
            assert_eq!(body["conf_threshold"], 0.37);
            assert!(body["hef_path"].as_str().unwrap().ends_with("yolov11n.hef"));
            drop(requests);

            source.frames_tx.send(red_bgr(1, 1)).unwrap();
            wait_for_error(&source, "source frame size mismatch").await;
            assert_eq!(state.metadata_calls.load(Ordering::Acquire), 1);
            assert_eq!(state.detect_calls.load(Ordering::Acquire), 1);
            assert_eq!(
                source.status().error,
                "source frame size mismatch: expected 1228800, got 3"
            );
            server.abort();
        });
    }

    #[test]
    fn metadata_cache_invalidates_for_every_model_hef_identity_field() {
        let key = HefKey {
            model_name: "yolov8n".to_string(),
            path: Some(PathBuf::from("model.hef")),
            size: Some(10),
            modified: Some(SystemTime::UNIX_EPOCH),
        };
        let cached = Some((key.clone(), 42));
        assert_eq!(cached_frame_size(&cached, &key), Some(42));
        for changed in [
            HefKey {
                model_name: "yolov11n".to_string(),
                ..key.clone()
            },
            HefKey {
                path: Some(PathBuf::from("other.hef")),
                ..key.clone()
            },
            HefKey {
                size: Some(11),
                ..key.clone()
            },
            HefKey {
                modified: Some(SystemTime::UNIX_EPOCH + Duration::from_secs(1)),
                ..key
            },
        ] {
            assert_eq!(cached_frame_size(&cached, &changed), None);
        }
    }

    #[test]
    fn single_in_flight_latest_slot_clears_results_and_matches_queue_status() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let state = StubState::default();
            state
                .detect_delays
                .lock()
                .await
                .push_back(Duration::from_millis(150));
            let (client, server) = stub(state.clone()).await;
            let pipeline = pipeline(client, json!({}), Duration::from_secs(1));
            let (detection_error, _) = watch::channel(None);
            let slot = Arc::new(LatestSlot {
                frame: Mutex::new(None),
                notify: Notify::new(),
                closed: AtomicBool::new(false),
                active: AtomicBool::new(true),
            });
            let consumer = pipeline.clone();
            let consumer_slot = Arc::clone(&slot);
            tokio::spawn(async move {
                consumer
                    .consume("cam".to_string(), consumer_slot, detection_error)
                    .await;
            });
            pipeline
                .enqueue(
                    &slot,
                    FrameInput {
                        bytes: red_bgr(1, 1),
                        width: 1,
                        height: 1,
                    },
                )
                .await;
            wait_for(&state.detect_in_flight, 1).await;
            pipeline
                .enqueue(
                    &slot,
                    FrameInput {
                        bytes: red_bgr(1, 1),
                        width: 1,
                        height: 1,
                    },
                )
                .await;
            pipeline
                .enqueue(
                    &slot,
                    FrameInput {
                        bytes: blue_bgr(1, 1),
                        width: 1,
                        height: 1,
                    },
                )
                .await;

            let snapshot = pipeline.snapshot().await;
            assert_eq!(snapshot.queue_size, 1);
            assert!(snapshot.result_sources.is_empty());
            assert_eq!(state.detect_calls.load(Ordering::Acquire), 1);
            assert_eq!(state.max_detect_in_flight.load(Ordering::Acquire), 1);

            tokio::time::advance(Duration::from_millis(150)).await;
            wait_for(&state.detect_calls, 2).await;
            wait_for_result(&pipeline, "cam", "latest slot").await;
            assert_eq!(pipeline.snapshot().await.queue_size, 0);
            assert_eq!(state.max_detect_in_flight.load(Ordering::Acquire), 1);
            assert_eq!((pipeline.snapshot().await.fps * 10.0).fract(), 0.0);
            let requests = state.requests.lock().await;
            let latest = STANDARD
                .decode(requests.last().unwrap()["input_base64"].as_str().unwrap())
                .unwrap();
            assert!(latest.as_chunks::<3>().0.iter().all(|&p| p == [0, 0, 255]));
            server.abort();
        });
    }

    #[test]
    fn metadata_and_detect_timeouts_clear_then_recover_latest_after_backoff() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let state = StubState::default();
            state
                .metadata_delays
                .lock()
                .await
                .push_back(Duration::from_millis(700));
            let (client, server) = stub(state.clone()).await;
            let pipeline = pipeline(client, json!({}), Duration::from_millis(300));
            let (source, _status) = source("cam", 1, 1);
            pipeline.attach("cam".to_string(), &source);

            source.frames_tx.send(red_bgr(1, 1)).unwrap();
            wait_for(&state.metadata_calls, 1).await;
            tokio::time::advance(Duration::from_millis(300)).await;
            wait_for_error(&source, "metadata timed out").await;
            source.frames_tx.send(red_bgr(1, 1)).unwrap();
            tokio::time::advance(Duration::from_millis(20)).await;
            wait_for(&state.metadata_calls, 2).await;
            wait_for(&state.detect_calls, 1).await;
            wait_for_result(&pipeline, "cam", "metadata recovery").await;

            state
                .detect_delays
                .lock()
                .await
                .push_back(Duration::from_millis(700));
            source.frames_tx.send(red_bgr(1, 1)).unwrap();
            wait_for(&state.detect_calls, 2).await;
            assert!(pipeline.snapshot().await.result_sources.is_empty());
            tokio::time::advance(Duration::from_millis(300)).await;
            wait_for_error(&source, "detection timed out").await;
            source.frames_tx.send(blue_bgr(1, 1)).unwrap();
            tokio::time::advance(Duration::from_millis(20)).await;
            wait_for(&state.detect_calls, 3).await;
            wait_for_result(&pipeline, "cam", "detect recovery").await;
            assert!(source.status().error.is_empty());
            let requests = state.requests.lock().await;
            let latest = STANDARD
                .decode(requests.last().unwrap()["input_base64"].as_str().unwrap())
                .unwrap();
            assert!(latest.as_chunks::<3>().0.iter().all(|&p| p == [0, 0, 255]));
            server.abort();
        });
    }

    #[test]
    fn source_count_policy_skips_real_requests_and_status_is_stable() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = StubState::default();
            let (client, server) = stub(state.clone()).await;
            let mut baseline = 0;
            for count in 1..=4 {
                let pipeline = pipeline(
                    client.clone(),
                    json!({"model": "yolov8n", "confidence_threshold": 0.42}),
                    Duration::from_secs(1),
                );
                let mut sources = Vec::new();
                let mut statuses = Vec::new();
                for index in (0..count).rev() {
                    let id = format!("cam-{index}");
                    let (source, status) = source(&id, 1, 1);
                    pipeline.attach(id, &source);
                    sources.push(source);
                    statuses.push(status);
                }
                tokio::time::timeout(Duration::from_secs(5), async {
                    while pipeline.snapshot().await.skip_rate != count - 1 {
                        tokio::task::yield_now().await;
                    }
                })
                .await
                .unwrap();
                let expected = 8usize.div_ceil(count);
                let started = baseline;
                for frame in 0..8 {
                    sources[0].frames_tx.send(red_bgr(1, 1)).unwrap();
                    if frame % count == 0 {
                        baseline += 1;
                        wait_for(&state.detect_calls, baseline).await;
                    }
                }
                for _ in 0..((count - (8 % count)) % count + 1) {
                    sources[0].frames_tx.send(red_bgr(1, 1)).unwrap();
                }
                baseline += 1;
                wait_for(&state.detect_calls, baseline).await;
                assert_eq!(baseline, state.detect_calls.load(Ordering::Acquire));
                assert_eq!(baseline - started, expected + 1);
                wait_for_result(
                    &pipeline,
                    &format!("cam-{}", count - 1),
                    "skip policy primary source",
                )
                .await;
                if count == 2 {
                    sources[1].frames_tx.send(red_bgr(1, 1)).unwrap();
                    baseline += 1;
                    wait_for(&state.detect_calls, baseline).await;
                    wait_for_result(&pipeline, "cam-0", "stable source order").await;
                }
                let snapshot = pipeline.snapshot().await;
                assert_eq!(snapshot.skip_rate, count - 1);
                assert_eq!(snapshot.model_name, "yolov8n");
                assert_eq!(snapshot.conf_threshold, 0.42);
                if count == 2 {
                    assert_eq!(snapshot.result_sources, ["cam-0", "cam-1"]);
                } else {
                    assert!(!snapshot.result_sources.is_empty());
                }
                assert_eq!((snapshot.fps * 10.0).fract(), 0.0);
                drop(statuses);
            }
            assert_eq!(skip_rate(0), 3);
            assert_eq!(skip_rate(1), 0);
            assert_eq!(skip_rate(2), 1);
            assert_eq!(skip_rate(3), 2);
            assert_eq!(skip_rate(8), 3);
            assert_eq!(REQUEST_TIMEOUT, Duration::from_secs(5));
            server.abort();
        });
    }

    fn pin_from(cargo_toml: &str) -> Result<String, String> {
        let manifest: toml::Value = cargo_toml.parse().map_err(|error| format!("{error}"))?;
        manifest
            .get("workspace")
            .and_then(|value| value.get("dependencies"))
            .and_then(|value| value.get("yu-infer"))
            .and_then(|value| value.get("rev"))
            .and_then(toml::Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| "yu-infer pin is missing".to_string())
    }

    fn pinned_router(cargo_toml: &str, checkouts: &std::path::Path) -> Result<String, String> {
        let pin = pin_from(cargo_toml)?;
        for repository in std::fs::read_dir(checkouts).map_err(|error| error.to_string())? {
            let repository = repository.map_err(|error| error.to_string())?;
            if !repository
                .file_name()
                .to_string_lossy()
                .starts_with("yu-hailo-infer-")
            {
                continue;
            }
            for checkout in
                std::fs::read_dir(repository.path()).map_err(|error| error.to_string())?
            {
                let checkout = checkout.map_err(|error| error.to_string())?;
                let revision = Command::new("git")
                    .args(["-C"])
                    .arg(checkout.path())
                    .args(["rev-parse", "HEAD"])
                    .output()
                    .map_err(|error| error.to_string())?;
                if revision.status.success()
                    && String::from_utf8_lossy(&revision.stdout).trim() == pin
                {
                    return std::fs::read_to_string(
                        checkout.path().join("yu-hailo-infer/src/router.rs"),
                    )
                    .map_err(|error| error.to_string());
                }
            }
        }
        Err(format!(
            "Cargo checkout for pinned revision {pin} was not found"
        ))
    }

    #[test]
    fn pinned_yu_infer_checkout_exposes_metadata_frame_size_contract() {
        run_bounded_test(TEST_TIMEOUT, async {
            let crates = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap();
            let cargo_toml = std::fs::read_to_string(crates.join("Cargo.toml")).unwrap();
            let cargo_home = std::env::var_os("CARGO_HOME")
                .map(PathBuf::from)
                .or_else(|| dirs::home_dir().map(|home| home.join(".cargo")))
                .unwrap();
            let checkouts = cargo_home.join("git/checkouts");
            let router = pinned_router(&cargo_toml, &checkouts).unwrap();
            assert!(router.contains(".route(\"/v1/infer/yolo/metadata\", get(yolo_metadata))"));
            assert!(router.contains("\"frame_size\": info.frame_size"));

            let wrong_pin = cargo_toml.replace(&pin_from(&cargo_toml).unwrap(), &"0".repeat(40));
            assert!(pinned_router(&wrong_pin, &checkouts).is_err());
        });
    }
}
