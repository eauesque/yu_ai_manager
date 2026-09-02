use std::{future::Future, pin::Pin, sync::Arc, time::Duration};

use bytes::Bytes;
use serde::Serialize;
use serde_json::Value;
use thiserror::Error;
use tokio::sync::{broadcast, mpsc, oneshot, watch, OwnedSemaphorePermit, Semaphore};

use super::{
    frame_source::{
        spawn_ffmpeg_supervisor, Clock, FfmpegFactory, SourceError, SupervisorEvent,
        SupervisorHandle, SystemClock,
    },
    input::{classify_source, validate_source, SourceKind},
    rules::StreamSourceConfig,
};

#[cfg(test)]
tokio::task_local! {
    static FFMPEG_SPAWN_OBSERVER: Arc<std::sync::atomic::AtomicUsize>;
}

#[cfg(test)]
pub(crate) async fn observe_ffmpeg_spawns<T>(
    observer: Arc<std::sync::atomic::AtomicUsize>,
    future: impl Future<Output = T>,
) -> T {
    FFMPEG_SPAWN_OBSERVER.scope(observer, future).await
}

const COMMAND_CAPACITY: usize = 8;
const FRAME_CAPACITY: usize = 2;
const SOURCE_TEST_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub(crate) enum SourceState {
    Idle,
    Connecting,
    Active,
    Reconnecting,
    Stopped,
    Error,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct Resolution {
    pub(crate) width: u32,
    pub(crate) height: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct SourceStatus {
    pub(crate) id: String,
    pub(crate) name: String,
    pub(crate) url: String,
    #[serde(rename = "type")]
    pub(crate) source_type: String,
    pub(crate) state: SourceState,
    pub(crate) resolution: Resolution,
    pub(crate) fps: f64,
    pub(crate) frame_count: u64,
    pub(crate) error: String,
}

impl SourceStatus {
    pub(crate) fn restored(config: &StreamSourceConfig) -> Self {
        Self {
            id: config.id.clone(),
            name: if config.name.is_empty() {
                config.id.clone()
            } else {
                config.name.clone()
            },
            url: config.url.clone(),
            source_type: source_type(&config.url).to_string(),
            state: SourceState::Idle,
            resolution: Resolution {
                width: 0,
                height: 0,
            },
            fps: 0.0,
            frame_count: 0,
            error: String::new(),
        }
    }
}

fn source_type(url: &str) -> &'static str {
    match classify_source(url) {
        Ok(SourceKind::UsbIndex(_)) => "usb",
        Ok(SourceKind::Remote(remote)) if remote.to_ascii_lowercase().starts_with("rtsp") => "rtsp",
        Ok(SourceKind::Remote(remote)) if remote.to_ascii_lowercase().starts_with("http") => "http",
        Ok(SourceKind::LocalFile(_) | SourceKind::Remote(_)) | Err(_) => "file",
    }
}

#[derive(Debug, Error, Eq, PartialEq)]
pub(crate) enum SourceTaskError {
    #[error("active source capacity reached")]
    Capacity,
    #[error("source task is unavailable")]
    Closed,
    #[error("source failed to start: {0}")]
    Start(String),
    #[error("source failed to stop: {0}")]
    Stop(String),
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(crate) struct SourceTestResult {
    pub(crate) ok: bool,
    pub(crate) resolution: Resolution,
}

pub(crate) enum SourceCommand {
    Start(oneshot::Sender<Result<SourceStatus, SourceTaskError>>),
    Stop(oneshot::Sender<Result<SourceStatus, SourceTaskError>>),
    Delete(oneshot::Sender<Result<(), SourceTaskError>>),
    Test(oneshot::Sender<Result<SourceTestResult, SourceTaskError>>),
}

#[derive(Clone)]
pub(crate) struct SourceHandle {
    pub(crate) cmd_tx: mpsc::Sender<SourceCommand>,
    pub(crate) status_rx: watch::Receiver<SourceStatus>,
    pub(crate) frames_tx: broadcast::Sender<Arc<Bytes>>,
    pub(super) detection_error: watch::Sender<Option<String>>,
}

impl SourceHandle {
    pub(crate) fn status(&self) -> SourceStatus {
        let mut status = self.status_rx.borrow().clone();
        if let Some(error) = self.detection_error.borrow().as_ref() {
            status.error.clone_from(error);
        }
        status
    }

    pub(crate) async fn start(&self) -> Result<SourceStatus, SourceTaskError> {
        self.request(SourceCommand::Start).await
    }

    pub(crate) async fn stop(&self) -> Result<SourceStatus, SourceTaskError> {
        self.request(SourceCommand::Stop).await
    }

    pub(crate) async fn delete(&self) -> Result<(), SourceTaskError> {
        self.request(SourceCommand::Delete).await
    }

    pub(crate) async fn test(&self) -> Result<SourceTestResult, SourceTaskError> {
        self.request(SourceCommand::Test).await
    }

    async fn request<T>(
        &self,
        command: impl FnOnce(oneshot::Sender<Result<T, SourceTaskError>>) -> SourceCommand,
    ) -> Result<T, SourceTaskError> {
        let (reply_tx, reply_rx) = oneshot::channel();
        self.cmd_tx
            .send(command(reply_tx))
            .await
            .map_err(|_| SourceTaskError::Closed)?;
        reply_rx.await.map_err(|_| SourceTaskError::Closed)?
    }
}

pub(super) trait SourceRuntime: Send {
    fn events(&mut self) -> &mut mpsc::UnboundedReceiver<SupervisorEvent>;
    fn request_stop(&self);
    fn wait(
        self: Box<Self>,
    ) -> Pin<Box<dyn Future<Output = Result<(), SourceError>> + Send + 'static>>;
}

impl SourceRuntime for SupervisorHandle {
    fn events(&mut self) -> &mut mpsc::UnboundedReceiver<SupervisorEvent> {
        &mut self.events
    }

    fn request_stop(&self) {
        SupervisorHandle::request_stop(self);
    }

    fn wait(
        self: Box<Self>,
    ) -> Pin<Box<dyn Future<Output = Result<(), SourceError>> + Send + 'static>> {
        Box::pin(async move { SupervisorHandle::wait(*self).await })
    }
}

pub(super) trait SourceFactory: Send + Sync {
    fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError>;
}

pub(super) struct ValidatedFfmpegFactory {
    url: String,
    settings: Arc<Value>,
    #[cfg(test)]
    spawn_observer: Option<Arc<std::sync::atomic::AtomicUsize>>,
}

impl ValidatedFfmpegFactory {
    pub(super) fn new(url: String, settings: Arc<Value>) -> Self {
        Self {
            url,
            settings,
            #[cfg(test)]
            spawn_observer: FFMPEG_SPAWN_OBSERVER.try_with(Arc::clone).ok(),
        }
    }
}

impl SourceFactory for ValidatedFfmpegFactory {
    fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError> {
        #[cfg(test)]
        if let Some(observer) = &self.spawn_observer {
            observer.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
        let source = validate_source(&self.url, &self.settings)
            .map_err(|_| SourceError::InvalidConfiguration)?;
        Ok(Box::new(spawn_ffmpeg_supervisor(FfmpegFactory::new(
            &source,
        )?)))
    }
}

pub(crate) struct SourceTask {
    cmd_rx: mpsc::Receiver<SourceCommand>,
    status_tx: watch::Sender<SourceStatus>,
    frames_tx: broadcast::Sender<Arc<Bytes>>,
    factory: Arc<dyn SourceFactory>,
    clock: Arc<dyn Clock>,
    active_slots: Arc<Semaphore>,
    active_permit: Option<OwnedSemaphorePermit>,
    running: Option<Box<dyn SourceRuntime>>,
    started_at: Option<Duration>,
}

enum TaskInput {
    Command(Option<SourceCommand>),
    Event(Option<SupervisorEvent>),
}

impl SourceTask {
    pub(super) fn spawn(
        config: StreamSourceConfig,
        factory: Arc<dyn SourceFactory>,
        active_slots: Arc<Semaphore>,
        clock: Arc<dyn Clock>,
    ) -> SourceHandle {
        let (cmd_tx, cmd_rx) = mpsc::channel(COMMAND_CAPACITY);
        let (status_tx, status_rx) = watch::channel(SourceStatus::restored(&config));
        let (frames_tx, _) = broadcast::channel(FRAME_CAPACITY);
        let (detection_error, _) = watch::channel(None);
        let task = Self {
            cmd_rx,
            status_tx,
            frames_tx: frames_tx.clone(),
            factory,
            clock,
            active_slots,
            active_permit: None,
            running: None,
            started_at: None,
        };
        tokio::spawn(task.run());
        SourceHandle {
            cmd_tx,
            status_rx,
            frames_tx,
            detection_error,
        }
    }

    pub(super) fn spawn_ffmpeg(
        config: StreamSourceConfig,
        settings: Arc<Value>,
        active_slots: Arc<Semaphore>,
    ) -> SourceHandle {
        let factory = Arc::new(ValidatedFfmpegFactory::new(config.url.clone(), settings));
        Self::spawn(
            config,
            factory,
            active_slots,
            Arc::new(SystemClock::default()),
        )
    }

    async fn run(mut self) {
        loop {
            let input = if let Some(runtime) = self.running.as_mut() {
                tokio::select! {
                    command = self.cmd_rx.recv() => TaskInput::Command(command),
                    event = runtime.events().recv() => TaskInput::Event(event),
                }
            } else {
                TaskInput::Command(self.cmd_rx.recv().await)
            };

            match input {
                TaskInput::Command(Some(command)) => {
                    if self.handle_command(command).await {
                        return;
                    }
                }
                TaskInput::Command(None) => {
                    let _ = self.stop_running().await;
                    return;
                }
                TaskInput::Event(Some(event)) => self.handle_event(event).await,
                TaskInput::Event(None) => self.finish_runtime().await,
            }
        }
    }

    async fn handle_command(&mut self, command: SourceCommand) -> bool {
        match command {
            SourceCommand::Start(reply) => {
                let _ = reply.send(self.start().await);
                false
            }
            SourceCommand::Stop(reply) => {
                let result = self.stop().await;
                let _ = reply.send(result);
                false
            }
            SourceCommand::Delete(reply) => {
                let result = self
                    .stop_running()
                    .await
                    .map_err(|error| SourceTaskError::Stop(error.to_string()));
                self.set_state(SourceState::Stopped, None);
                let _ = reply.send(result);
                true
            }
            SourceCommand::Test(reply) => {
                let _ = reply.send(self.test_source().await);
                false
            }
        }
    }

    async fn start(&mut self) -> Result<SourceStatus, SourceTaskError> {
        if self.running.is_some() {
            return Ok(self.status());
        }
        let permit = Arc::clone(&self.active_slots)
            .try_acquire_owned()
            .map_err(|_| SourceTaskError::Capacity)?;
        self.update_status(|status| {
            status.state = SourceState::Connecting;
            status.fps = 0.0;
            status.frame_count = 0;
            status.error.clear();
        });
        match self.factory.spawn() {
            Ok(runtime) => {
                self.active_permit = Some(permit);
                self.running = Some(runtime);
                self.started_at = Some(self.clock.now());
                Ok(self.status())
            }
            Err(error) => {
                drop(permit);
                let message = error.to_string();
                self.set_state(SourceState::Error, Some(message.clone()));
                Err(SourceTaskError::Start(message))
            }
        }
    }

    async fn stop(&mut self) -> Result<SourceStatus, SourceTaskError> {
        let result = self.stop_running().await;
        self.set_state(SourceState::Stopped, None);
        result
            .map(|()| self.status())
            .map_err(|error| SourceTaskError::Stop(error.to_string()))
    }

    async fn stop_running(&mut self) -> Result<(), SourceError> {
        let result = if let Some(runtime) = self.running.take() {
            runtime.request_stop();
            runtime.wait().await
        } else {
            Ok(())
        };
        self.active_permit.take();
        self.started_at = None;
        result
    }

    async fn test_source(&mut self) -> Result<SourceTestResult, SourceTaskError> {
        if self.running.is_some() {
            let status = self.status();
            return Ok(SourceTestResult {
                ok: status.state == SourceState::Active,
                resolution: status.resolution,
            });
        }
        let _permit = Arc::clone(&self.active_slots)
            .try_acquire_owned()
            .map_err(|_| SourceTaskError::Capacity)?;
        let mut runtime = self
            .factory
            .spawn()
            .map_err(|error| SourceTaskError::Start(error.to_string()))?;
        let outcome = tokio::time::timeout(SOURCE_TEST_TIMEOUT, async {
            loop {
                match runtime.events().recv().await {
                    Some(SupervisorEvent::Connected { width, height, .. })
                    | Some(SupervisorEvent::Frame(super::frame_source::Frame {
                        width,
                        height,
                        ..
                    })) => {
                        break Ok(SourceTestResult {
                            ok: true,
                            resolution: Resolution { width, height },
                        });
                    }
                    Some(SupervisorEvent::Error(error)) => {
                        break Err(SourceTaskError::Start(error.to_string()));
                    }
                    Some(SupervisorEvent::Ended | SupervisorEvent::Stopped) | None => {
                        break Ok(SourceTestResult {
                            ok: false,
                            resolution: Resolution {
                                width: 0,
                                height: 0,
                            },
                        });
                    }
                    Some(SupervisorEvent::Reconnecting { .. }) => {}
                }
            }
        })
        .await
        .map_err(|_| SourceTaskError::Start("source test timed out".to_string()));
        runtime.request_stop();
        let _ = runtime.wait().await;
        outcome?
    }

    async fn handle_event(&mut self, event: SupervisorEvent) {
        match event {
            SupervisorEvent::Connected { width, height, .. } => {
                self.update_status(|status| {
                    status.state = SourceState::Active;
                    status.resolution = Resolution { width, height };
                    status.error.clear();
                });
            }
            SupervisorEvent::Frame(frame) => {
                let now = self.clock.now();
                let started_at = self.started_at;
                let width = frame.width;
                let height = frame.height;
                self.update_status(|status| {
                    status.state = SourceState::Active;
                    status.resolution = Resolution { width, height };
                    status.frame_count = status.frame_count.saturating_add(1);
                    let elapsed =
                        started_at.map_or(0.0, |start| now.saturating_sub(start).as_secs_f64());
                    status.fps = if elapsed > 0.0 {
                        (status.frame_count as f64 / elapsed * 10.0).round() / 10.0
                    } else {
                        0.0
                    };
                });
                let _ = self.frames_tx.send(Arc::new(Bytes::from(frame.bytes)));
            }
            SupervisorEvent::Reconnecting { .. } => {
                self.set_state(SourceState::Reconnecting, None);
            }
            SupervisorEvent::Ended | SupervisorEvent::Stopped => {
                let _ = self.stop_running().await;
                self.set_state(SourceState::Stopped, None);
            }
            SupervisorEvent::Error(error) => {
                let message = error.to_string();
                let _ = self.stop_running().await;
                self.set_state(SourceState::Error, Some(message));
            }
        }
    }

    async fn finish_runtime(&mut self) {
        let result = self.stop_running().await;
        match result {
            Ok(()) => self.set_state(SourceState::Stopped, None),
            Err(error) => self.set_state(SourceState::Error, Some(error.to_string())),
        }
    }

    fn status(&self) -> SourceStatus {
        self.status_tx.borrow().clone()
    }

    fn set_state(&mut self, state: SourceState, error: Option<String>) {
        self.update_status(|status| {
            status.state = state;
            if let Some(error) = error {
                status.error = error;
            }
        });
    }

    fn update_status(&mut self, update: impl FnOnce(&mut SourceStatus)) {
        let mut status = self.status();
        update(&mut status);
        self.status_tx.send_replace(status);
    }
}

#[cfg(test)]
pub(super) mod tests {
    use std::{
        collections::VecDeque,
        sync::{
            atomic::{AtomicBool, AtomicUsize, Ordering},
            Condvar, Mutex,
        },
    };

    use super::super::frame_source::{FrameSource, SyntheticSource};
    use super::super::{run_bounded_paused_test, run_bounded_test};
    use super::*;

    const TEST_TIMEOUT: Duration = Duration::from_secs(3);

    #[derive(Default)]
    pub(crate) struct ManualClock {
        now: Mutex<Duration>,
        token: Mutex<u64>,
        wake: Condvar,
    }

    impl Clock for ManualClock {
        fn now(&self) -> Duration {
            *self.now.lock().unwrap_or_else(|error| error.into_inner())
        }

        fn token(&self) -> u64 {
            *self.token.lock().unwrap_or_else(|error| error.into_inner())
        }

        fn notify(&self) {
            let mut token = self.token.lock().unwrap_or_else(|error| error.into_inner());
            *token = token.wrapping_add(1);
            self.wake.notify_all();
        }

        fn wait_until(&self, deadline: Duration, token: u64) {
            let mut current = self.token.lock().unwrap_or_else(|error| error.into_inner());
            while *current == token && self.now() < deadline {
                current = self
                    .wake
                    .wait(current)
                    .unwrap_or_else(|error| error.into_inner());
            }
        }
    }

    struct SyntheticRuntime {
        events: mpsc::UnboundedReceiver<SupervisorEvent>,
        stop: Arc<AtomicBool>,
        clock: Arc<dyn Clock>,
        task: tokio::task::JoinHandle<Result<(), SourceError>>,
    }

    impl SourceRuntime for SyntheticRuntime {
        fn events(&mut self) -> &mut mpsc::UnboundedReceiver<SupervisorEvent> {
            &mut self.events
        }

        fn request_stop(&self) {
            self.stop.store(true, Ordering::Release);
            self.clock.notify();
        }

        fn wait(
            self: Box<Self>,
        ) -> Pin<Box<dyn Future<Output = Result<(), SourceError>> + Send + 'static>> {
            Box::pin(async move { self.task.await.map_err(|_| SourceError::ReaderPanicked)? })
        }
    }

    pub(crate) struct SyntheticFactory {
        sources: Mutex<VecDeque<Box<dyn FrameSource>>>,
        starts: AtomicUsize,
        clock: Arc<dyn Clock>,
        emit_late_frame: bool,
        initial_reconnecting: bool,
        width: u32,
        height: u32,
    }

    impl SyntheticFactory {
        pub(crate) fn new(
            clock: Arc<dyn Clock>,
            source_count: usize,
            emit_late_frame: bool,
        ) -> Arc<Self> {
            Self::build(clock, source_count, emit_late_frame, false)
        }

        pub(crate) fn reconnecting(clock: Arc<dyn Clock>) -> Arc<Self> {
            Self::build(clock, 1, false, true)
        }

        fn build(
            clock: Arc<dyn Clock>,
            source_count: usize,
            emit_late_frame: bool,
            initial_reconnecting: bool,
        ) -> Arc<Self> {
            let sources = (0..source_count)
                .map(|_| Box::new(SyntheticSource::finite(2, 2, 2)) as Box<dyn FrameSource>)
                .collect();
            Arc::new(Self {
                sources: Mutex::new(sources),
                starts: AtomicUsize::new(0),
                clock,
                emit_late_frame,
                initial_reconnecting,
                width: 2,
                height: 2,
            })
        }

        pub(crate) fn starts(&self) -> usize {
            self.starts.load(Ordering::Relaxed)
        }
    }

    impl SourceFactory for SyntheticFactory {
        fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError> {
            let mut source = self
                .sources
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .pop_front()
                .ok_or(SourceError::InvalidConfiguration)?;
            self.starts.fetch_add(1, Ordering::Relaxed);
            let stop = Arc::new(AtomicBool::new(false));
            let task_stop = Arc::clone(&stop);
            let clock = Arc::clone(&self.clock);
            let task_clock = Arc::clone(&clock);
            let emit_late_frame = self.emit_late_frame;
            let (events_tx, events) = mpsc::unbounded_channel();
            let initial_event = if self.initial_reconnecting {
                SupervisorEvent::Reconnecting {
                    failures: 1,
                    backoff: Duration::from_secs(1),
                }
            } else {
                SupervisorEvent::Connected {
                    pid: None,
                    width: self.width,
                    height: self.height,
                }
            };
            events_tx
                .send(initial_event)
                .map_err(|_| SourceError::Interrupted)?;
            let task = tokio::task::spawn_blocking(move || {
                if !task_stop.load(Ordering::Acquire) {
                    let token = task_clock.token();
                    if !task_stop.load(Ordering::Acquire) {
                        task_clock.wait_until(task_clock.now() + Duration::from_secs(1), token);
                    }
                }
                if task_stop.load(Ordering::Acquire) {
                    if emit_late_frame {
                        if let Some(frame) = source.next_frame()? {
                            let _ = events_tx.send(SupervisorEvent::Frame(frame));
                        }
                    }
                    let _ = events_tx.send(SupervisorEvent::Stopped);
                    return Ok(());
                }
                while let Some(frame) = source.next_frame()? {
                    if events_tx.send(SupervisorEvent::Frame(frame)).is_err() {
                        return Ok(());
                    }
                }
                let _ = events_tx.send(SupervisorEvent::Ended);
                Ok(())
            });
            Ok(Box::new(SyntheticRuntime {
                events,
                stop,
                clock,
                task,
            }))
        }
    }

    struct SilentRuntime {
        events: mpsc::UnboundedReceiver<SupervisorEvent>,
        _events_tx: mpsc::UnboundedSender<SupervisorEvent>,
        stopped: Arc<AtomicBool>,
    }

    impl SourceRuntime for SilentRuntime {
        fn events(&mut self) -> &mut mpsc::UnboundedReceiver<SupervisorEvent> {
            &mut self.events
        }

        fn request_stop(&self) {
            self.stopped.store(true, Ordering::Release);
        }

        fn wait(
            self: Box<Self>,
        ) -> Pin<Box<dyn Future<Output = Result<(), SourceError>> + Send + 'static>> {
            Box::pin(async { Ok(()) })
        }
    }

    struct SilentFactory(Arc<AtomicBool>);

    impl SourceFactory for SilentFactory {
        fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError> {
            let (events_tx, events) = mpsc::unbounded_channel();
            Ok(Box::new(SilentRuntime {
                events,
                _events_tx: events_tx,
                stopped: Arc::clone(&self.0),
            }))
        }
    }

    fn config() -> StreamSourceConfig {
        StreamSourceConfig {
            id: "cam".to_string(),
            url: "rtsp://camera.test/live".to_string(),
            name: String::new(),
        }
    }

    #[test]
    fn lifecycle_is_serial_and_late_frames_cannot_revive_stopped_state() {
        run_bounded_test(TEST_TIMEOUT, async {
            let clock: Arc<dyn Clock> = Arc::new(ManualClock::default());
            let factory = SyntheticFactory::new(Arc::clone(&clock), 2, true);
            let handle = SourceTask::spawn(
                config(),
                factory.clone(),
                Arc::new(Semaphore::new(4)),
                clock,
            );

            handle.start().await.unwrap();
            handle.start().await.unwrap();
            assert_eq!(factory.starts(), 1);
            let stopped = handle.stop().await.unwrap();
            assert_eq!(stopped.state, SourceState::Stopped);
            assert_eq!(stopped.frame_count, 0);
            tokio::task::yield_now().await;
            assert_eq!(handle.status().state, SourceState::Stopped);
            assert_eq!(handle.status().frame_count, 0);
        });
    }

    #[test]
    fn source_test_timeout_stops_its_runtime() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let stopped = Arc::new(AtomicBool::new(false));
            let handle = SourceTask::spawn(
                config(),
                Arc::new(SilentFactory(Arc::clone(&stopped))),
                Arc::new(Semaphore::new(1)),
                Arc::new(ManualClock::default()),
            );
            let test = tokio::spawn(async move { handle.test().await });
            tokio::task::yield_now().await;
            tokio::time::advance(SOURCE_TEST_TIMEOUT).await;
            assert_eq!(
                test.await.unwrap(),
                Err(SourceTaskError::Start("source test timed out".to_string()))
            );
            assert!(stopped.load(Ordering::Acquire));
        });
    }
}
