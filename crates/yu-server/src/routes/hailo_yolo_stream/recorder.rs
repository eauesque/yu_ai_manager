use std::{
    collections::{BTreeMap, HashMap},
    ffi::CString,
    io,
    path::{Path, PathBuf},
    process::Stdio,
    sync::Arc,
    time::{Duration, Instant as StdInstant},
};

use async_trait::async_trait;
use bytes::Bytes;
use chrono::Local;
use serde::Serialize;
use tokio::{
    io::AsyncWriteExt,
    process::{Child, ChildStdin, Command},
    sync::{mpsc, oneshot},
};

const COMMAND_CAPACITY: usize = 32;
const MAX_CONCURRENT: usize = 4;
const MIN_FREE_BYTES: u64 = 500 * 1024 * 1024;
const MONITOR_INTERVAL: Duration = Duration::from_secs(1);
const STOP_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone)]
pub(crate) struct Recorder {
    tx: mpsc::Sender<RecorderCommand>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ExtendMode {
    Fixed,
    Extend,
    ExtendMax,
}

impl ExtendMode {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "fixed" => Ok(Self::Fixed),
            "extend" => Ok(Self::Extend),
            "extend_max" => Ok(Self::ExtendMax),
            _ => Err(format!("Invalid extend_mode: {value}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Fixed => "fixed",
            Self::Extend => "extend",
            Self::ExtendMax => "extend_max",
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct RecordingRequest {
    pub(crate) source_id: String,
    pub(crate) save_dir: PathBuf,
    pub(crate) duration: Duration,
    pub(crate) max_duration: Duration,
    pub(crate) extend_mode: String,
    pub(crate) width: u32,
    pub(crate) height: u32,
    pub(crate) fps: f64,
}

#[derive(Debug, Eq, PartialEq)]
pub(crate) enum TriggerState {
    Started,
    Extended,
}

#[derive(Debug, Eq, PartialEq)]
pub(crate) struct TriggerResult {
    pub(crate) state: TriggerState,
    pub(crate) path: String,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub(crate) struct RecorderStatus {
    pub(crate) source_id: String,
    pub(crate) path: String,
    pub(crate) extend_mode: String,
    pub(crate) elapsed_sec: f64,
    pub(crate) remaining_sec: f64,
    pub(crate) frame_count: u64,
}

struct RecordingSession {
    source_id: String,
    path: String,
    child: Box<dyn RecordingChild>,
    extend_mode: ExtendMode,
    duration: Duration,
    max_duration: Duration,
    started_at: Duration,
    deadline: Duration,
    frame_count: u64,
}

enum RecorderCommand {
    Trigger {
        request: RecordingRequest,
        frame: Bytes,
        reply: oneshot::Sender<Result<TriggerResult, String>>,
    },
    Stop {
        source_id: String,
        reply: oneshot::Sender<bool>,
    },
    Status {
        reply: oneshot::Sender<BTreeMap<String, RecorderStatus>>,
    },
    Tick {
        reply: Option<oneshot::Sender<()>>,
    },
    Shutdown {
        reply: oneshot::Sender<()>,
    },
    #[cfg(test)]
    Hold {
        entered: oneshot::Sender<()>,
        release: oneshot::Receiver<()>,
    },
}

#[async_trait]
trait RecorderIo: Send + Sync {
    async fn free_bytes(&self, directory: &Path) -> io::Result<u64>;
    async fn spawn(
        &self,
        path: &Path,
        width: u32,
        height: u32,
        fps: f64,
    ) -> io::Result<Box<dyn RecordingChild>>;
}

#[async_trait]
trait RecordingChild: Send {
    async fn write_frame(&mut self, frame: &[u8]) -> io::Result<()>;
    async fn finish(&mut self, timeout: Duration) -> io::Result<()>;
}

trait RecorderClock: Send + Sync {
    fn now(&self) -> Duration;
    fn timestamp(&self) -> String;
}

struct SystemClock {
    started_at: StdInstant,
}

impl Default for SystemClock {
    fn default() -> Self {
        Self {
            started_at: StdInstant::now(),
        }
    }
}

impl RecorderClock for SystemClock {
    fn now(&self) -> Duration {
        self.started_at.elapsed()
    }

    fn timestamp(&self) -> String {
        Local::now().format("%Y-%m-%d_%H%M%S").to_string()
    }
}

struct SystemIo;

#[async_trait]
impl RecorderIo for SystemIo {
    async fn free_bytes(&self, directory: &Path) -> io::Result<u64> {
        tokio::fs::create_dir_all(directory).await?;
        available_space(directory)
    }

    async fn spawn(
        &self,
        path: &Path,
        width: u32,
        height: u32,
        fps: f64,
    ) -> io::Result<Box<dyn RecordingChild>> {
        let mut child = Command::new("ffmpeg")
            .args([
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-s",
                &format!("{width}x{height}"),
                "-r",
                &fps.to_string(),
                "-i",
                "pipe:0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
            ])
            .arg(path)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| io::Error::other("ffmpeg stdin unavailable"))?;
        Ok(Box::new(FfmpegChild {
            stdin: Some(stdin),
            child,
        }))
    }
}

struct FfmpegChild {
    stdin: Option<ChildStdin>,
    child: Child,
}

#[async_trait]
impl RecordingChild for FfmpegChild {
    async fn write_frame(&mut self, frame: &[u8]) -> io::Result<()> {
        self.stdin
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "ffmpeg stdin closed"))?
            .write_all(frame)
            .await
    }

    async fn finish(&mut self, timeout: Duration) -> io::Result<()> {
        self.stdin.take();
        match tokio::time::timeout(timeout, self.child.wait()).await {
            Ok(result) => {
                result?;
                Ok(())
            }
            Err(_) => {
                self.child.kill().await?;
                self.child.wait().await?;
                Ok(())
            }
        }
    }
}

struct RecorderTask {
    rx: mpsc::Receiver<RecorderCommand>,
    io: Arc<dyn RecorderIo>,
    clock: Arc<dyn RecorderClock>,
    sessions: HashMap<String, RecordingSession>,
}

impl Recorder {
    pub(crate) fn spawn() -> Self {
        Self::spawn_with(Arc::new(SystemIo), Arc::new(SystemClock::default()), true)
    }

    fn spawn_with(io: Arc<dyn RecorderIo>, clock: Arc<dyn RecorderClock>, monitor: bool) -> Self {
        let (tx, rx) = mpsc::channel(COMMAND_CAPACITY);
        tokio::spawn(
            RecorderTask {
                rx,
                io,
                clock,
                sessions: HashMap::new(),
            }
            .run(),
        );
        if monitor {
            let monitor_tx = tx.clone();
            tokio::spawn(async move {
                let mut interval = tokio::time::interval(MONITOR_INTERVAL);
                interval.tick().await;
                loop {
                    interval.tick().await;
                    if monitor_tx
                        .send(RecorderCommand::Tick { reply: None })
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
            });
        }
        Self { tx }
    }

    pub(crate) async fn trigger(
        &self,
        request: RecordingRequest,
        frame: Bytes,
    ) -> Result<TriggerResult, String> {
        let (reply_tx, reply_rx) = oneshot::channel();
        self.tx
            .send(RecorderCommand::Trigger {
                request,
                frame,
                reply: reply_tx,
            })
            .await
            .map_err(|_| "Recorder unavailable".to_string())?;
        reply_rx
            .await
            .map_err(|_| "Recorder unavailable".to_string())?
    }

    pub(crate) async fn stop_source(&self, source_id: &str) -> bool {
        let (reply_tx, reply_rx) = oneshot::channel();
        if self
            .tx
            .send(RecorderCommand::Stop {
                source_id: source_id.to_string(),
                reply: reply_tx,
            })
            .await
            .is_err()
        {
            return false;
        }
        reply_rx.await.unwrap_or(false)
    }

    pub(crate) async fn status(&self) -> BTreeMap<String, RecorderStatus> {
        let (reply_tx, reply_rx) = oneshot::channel();
        if self
            .tx
            .send(RecorderCommand::Status { reply: reply_tx })
            .await
            .is_err()
        {
            return BTreeMap::new();
        }
        reply_rx.await.unwrap_or_default()
    }

    pub(crate) async fn shutdown(&self) {
        let (reply_tx, reply_rx) = oneshot::channel();
        if self
            .tx
            .send(RecorderCommand::Shutdown { reply: reply_tx })
            .await
            .is_ok()
        {
            let _ = reply_rx.await;
        }
    }
}

impl RecorderTask {
    async fn run(mut self) {
        while let Some(command) = self.rx.recv().await {
            match command {
                RecorderCommand::Trigger {
                    request,
                    frame,
                    reply,
                } => {
                    let result = self.trigger(request, frame).await;
                    let _ = reply.send(result);
                }
                RecorderCommand::Stop { source_id, reply } => {
                    let _ = reply.send(self.stop(&source_id).await);
                }
                RecorderCommand::Status { reply } => {
                    let _ = reply.send(self.status());
                }
                RecorderCommand::Tick { reply } => {
                    self.stop_expired().await;
                    if let Some(reply) = reply {
                        let _ = reply.send(());
                    }
                }
                RecorderCommand::Shutdown { reply } => {
                    self.stop_all().await;
                    let _ = reply.send(());
                    break;
                }
                #[cfg(test)]
                RecorderCommand::Hold { entered, release } => {
                    let _ = entered.send(());
                    let _ = release.await;
                }
            }
        }
        self.stop_all().await;
    }

    async fn trigger(
        &mut self,
        request: RecordingRequest,
        frame: Bytes,
    ) -> Result<TriggerResult, String> {
        validate_request(&request)?;
        let now = self.clock.now();
        if let Some(session) = self.sessions.get_mut(&request.source_id) {
            extend_deadline(session, now);
            let path = session.path.clone();
            if let Err(error) = session.child.write_frame(&frame).await {
                self.finish_broken(&request.source_id).await;
                return Err(format!("Recording pipe failed: {error}"));
            }
            session.frame_count += 1;
            return Ok(TriggerResult {
                state: TriggerState::Extended,
                path,
            });
        }
        if self.sessions.len() >= MAX_CONCURRENT {
            return Err("Max concurrent recordings reached".to_string());
        }
        if self
            .io
            .free_bytes(&request.save_dir)
            .await
            .map_err(|error| format!("Cannot check disk space: {error}"))?
            < MIN_FREE_BYTES
        {
            return Err("Insufficient disk space".to_string());
        }
        let extend_mode = ExtendMode::parse(&request.extend_mode)?;
        let filename = recording_filename(&self.clock.timestamp(), &request.source_id);
        let output_path = request.save_dir.join(filename);
        let path = output_path.to_string_lossy().into_owned();
        let child = self
            .io
            .spawn(&output_path, request.width, request.height, request.fps)
            .await
            .map_err(|error| {
                if error.kind() == io::ErrorKind::NotFound {
                    "ffmpeg not found on PATH".to_string()
                } else {
                    format!("Cannot start ffmpeg: {error}")
                }
            })?;
        self.sessions.insert(
            request.source_id.clone(),
            RecordingSession {
                source_id: request.source_id.clone(),
                path: path.clone(),
                child,
                extend_mode,
                duration: request.duration,
                max_duration: request.max_duration,
                started_at: now,
                deadline: now.saturating_add(request.duration),
                frame_count: 0,
            },
        );
        let session = self.sessions.get_mut(&request.source_id).unwrap();
        if let Err(error) = session.child.write_frame(&frame).await {
            self.finish_broken(&request.source_id).await;
            return Err(format!("Recording pipe failed: {error}"));
        }
        session.frame_count = 1;
        Ok(TriggerResult {
            state: TriggerState::Started,
            path,
        })
    }

    async fn finish_broken(&mut self, source_id: &str) {
        if let Some(mut session) = self.sessions.remove(source_id) {
            let _ = session.child.finish(STOP_TIMEOUT).await;
        }
    }

    async fn stop(&mut self, source_id: &str) -> bool {
        let Some(mut session) = self.sessions.remove(source_id) else {
            return false;
        };
        if let Err(error) = session.child.finish(STOP_TIMEOUT).await {
            tracing::warn!(%source_id, %error, "failed to finalize Hailo YOLO recording");
        }
        true
    }

    async fn stop_expired(&mut self) {
        let now = self.clock.now();
        let expired: Vec<_> = self
            .sessions
            .iter()
            .filter(|(_, session)| now >= session.deadline)
            .map(|(source_id, _)| source_id.clone())
            .collect();
        for source_id in expired {
            self.stop(&source_id).await;
        }
    }

    async fn stop_all(&mut self) {
        let source_ids: Vec<_> = self.sessions.keys().cloned().collect();
        for source_id in source_ids {
            self.stop(&source_id).await;
        }
    }

    fn status(&self) -> BTreeMap<String, RecorderStatus> {
        let now = self.clock.now();
        self.sessions
            .iter()
            .map(|(source_id, session)| {
                (
                    source_id.clone(),
                    RecorderStatus {
                        source_id: session.source_id.clone(),
                        path: session.path.clone(),
                        extend_mode: session.extend_mode.as_str().to_string(),
                        elapsed_sec: tenths(now.saturating_sub(session.started_at)),
                        remaining_sec: tenths(session.deadline.saturating_sub(now)),
                        frame_count: session.frame_count,
                    },
                )
            })
            .collect()
    }
}

fn validate_request(request: &RecordingRequest) -> Result<(), String> {
    ExtendMode::parse(&request.extend_mode)?;
    if request.width == 0 || request.height == 0 {
        return Err("width and height must be positive".to_string());
    }
    if request.duration.is_zero() || request.max_duration.is_zero() {
        return Err("duration_sec and max_duration_sec must be positive".to_string());
    }
    if !request.fps.is_finite() || request.fps <= 0.0 {
        return Err("fps must be positive".to_string());
    }
    Ok(())
}

fn extend_deadline(session: &mut RecordingSession, now: Duration) {
    match session.extend_mode {
        ExtendMode::Fixed => {}
        ExtendMode::Extend => session.deadline = now.saturating_add(session.duration),
        ExtendMode::ExtendMax => {
            session.deadline = now
                .saturating_add(session.duration)
                .min(session.started_at.saturating_add(session.max_duration));
        }
    }
}

fn recording_filename(timestamp: &str, source_id: &str) -> String {
    let mut safe_id = source_id.replace(['/', '\\'], "_");
    while safe_id.contains("..") {
        safe_id = safe_id.replace("..", "_");
    }
    format!("{timestamp}_{safe_id}.mp4")
}

fn tenths(duration: Duration) -> f64 {
    (duration.as_secs_f64() * 10.0).round() / 10.0
}

#[cfg(unix)]
fn available_space(path: &Path) -> io::Result<u64> {
    use std::os::unix::ffi::OsStrExt;

    let path = CString::new(path.as_os_str().as_bytes())
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "path contains NUL"))?;
    let mut stats = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    // SAFETY: `path` is NUL-terminated and `stats` points to writable storage.
    if unsafe { libc::statvfs(path.as_ptr(), stats.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: successful `statvfs` initialized `stats`.
    let stats = unsafe { stats.assume_init() };
    // Widen before multiplying: these fields are both u64 on Linux, but on
    // macOS `f_bavail` is u32 while `f_frsize` is u64. Each conversion is
    // therefore a no-op on some target and load-bearing on another.
    #[allow(clippy::useless_conversion)]
    let bytes = u64::from(stats.f_bavail).saturating_mul(u64::from(stats.f_frsize));
    Ok(bytes)
}

#[cfg(windows)]
fn available_space(path: &Path) -> io::Result<u64> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;

    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut available = 0_u64;
    // SAFETY: `wide` is NUL-terminated and `available` is a valid output pointer.
    if unsafe {
        GetDiskFreeSpaceExW(
            wide.as_ptr(),
            &mut available,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(available)
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashSet,
        process::Command as StdCommand,
        sync::{
            atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
            Mutex,
        },
    };

    use tempfile::TempDir;
    use tokio::sync::{Barrier, Notify};

    use super::*;
    use crate::routes::hailo_yolo_stream::{run_bounded_paused_test, run_bounded_test};

    const TEST_TIMEOUT: Duration = Duration::from_secs(12);

    struct FakeClock {
        millis: AtomicU64,
        timestamp: String,
    }

    impl FakeClock {
        fn new() -> Self {
            Self {
                millis: AtomicU64::new(0),
                timestamp: "2026-08-13_142536".to_string(),
            }
        }

        fn advance(&self, duration: Duration) {
            self.millis.fetch_add(
                u64::try_from(duration.as_millis()).unwrap(),
                Ordering::SeqCst,
            );
        }
    }

    impl RecorderClock for FakeClock {
        fn now(&self) -> Duration {
            Duration::from_millis(self.millis.load(Ordering::SeqCst))
        }

        fn timestamp(&self) -> String {
            self.timestamp.clone()
        }
    }

    #[derive(Default)]
    struct ChildProbe {
        writes: AtomicUsize,
        stdin_closed: AtomicBool,
        waited: AtomicBool,
        killed: AtomicBool,
    }

    struct FakeIo {
        free_bytes: AtomicU64,
        spawn_count: AtomicUsize,
        break_next: AtomicBool,
        hang_sources: Mutex<HashSet<String>>,
        probes: Mutex<Vec<(PathBuf, Arc<ChildProbe>)>>,
    }

    impl FakeIo {
        fn new(free_bytes: u64) -> Self {
            Self {
                free_bytes: AtomicU64::new(free_bytes),
                spawn_count: AtomicUsize::new(0),
                break_next: AtomicBool::new(false),
                hang_sources: Mutex::new(HashSet::new()),
                probes: Mutex::new(Vec::new()),
            }
        }

        fn probes(&self) -> Vec<Arc<ChildProbe>> {
            self.probes
                .lock()
                .unwrap()
                .iter()
                .map(|(_, probe)| Arc::clone(probe))
                .collect()
        }
    }

    #[async_trait]
    impl RecorderIo for FakeIo {
        async fn free_bytes(&self, _directory: &Path) -> io::Result<u64> {
            Ok(self.free_bytes.load(Ordering::SeqCst))
        }

        async fn spawn(
            &self,
            path: &Path,
            _width: u32,
            _height: u32,
            _fps: f64,
        ) -> io::Result<Box<dyn RecordingChild>> {
            self.spawn_count.fetch_add(1, Ordering::SeqCst);
            let probe = Arc::new(ChildProbe::default());
            let hang = self
                .hang_sources
                .lock()
                .unwrap()
                .iter()
                .any(|source| path.to_string_lossy().contains(source));
            self.probes
                .lock()
                .unwrap()
                .push((path.to_path_buf(), Arc::clone(&probe)));
            Ok(Box::new(FakeChild {
                probe,
                broken: self.break_next.swap(false, Ordering::SeqCst),
                hang,
            }))
        }
    }

    struct FakeChild {
        probe: Arc<ChildProbe>,
        broken: bool,
        hang: bool,
    }

    #[async_trait]
    impl RecordingChild for FakeChild {
        async fn write_frame(&mut self, _frame: &[u8]) -> io::Result<()> {
            if self.broken {
                return Err(io::Error::new(io::ErrorKind::BrokenPipe, "injected"));
            }
            self.probe.writes.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }

        async fn finish(&mut self, _timeout: Duration) -> io::Result<()> {
            self.probe.stdin_closed.store(true, Ordering::SeqCst);
            self.probe.waited.store(true, Ordering::SeqCst);
            self.probe.killed.store(self.hang, Ordering::SeqCst);
            Ok(())
        }
    }

    fn fixture(free_bytes: u64) -> (Recorder, Arc<FakeClock>, Arc<FakeIo>) {
        let clock = Arc::new(FakeClock::new());
        let io = Arc::new(FakeIo::new(free_bytes));
        let recorder = Recorder::spawn_with(io.clone(), clock.clone(), false);
        (recorder, clock, io)
    }

    fn request(source_id: &str, mode: &str) -> RecordingRequest {
        RecordingRequest {
            source_id: source_id.to_string(),
            save_dir: PathBuf::from("/recordings"),
            duration: Duration::from_secs(10),
            max_duration: Duration::from_secs(12),
            extend_mode: mode.to_string(),
            width: 2,
            height: 2,
            fps: 15.0,
        }
    }

    async fn trigger(recorder: &Recorder, source_id: &str, mode: &str) -> TriggerResult {
        recorder
            .trigger(request(source_id, mode), Bytes::from_static(&[0; 12]))
            .await
            .unwrap()
    }

    #[test]
    fn fake_clock_and_filesystem_fix_deadlines_capacity_and_disk_floor() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (recorder, clock, io) = fixture(MIN_FREE_BYTES - 1);
            assert_eq!(
                recorder
                    .trigger(request("low", "fixed"), Bytes::from_static(&[0; 12]))
                    .await
                    .unwrap_err(),
                "Insufficient disk space"
            );
            assert_eq!(io.spawn_count.load(Ordering::SeqCst), 0);
            io.free_bytes.store(MIN_FREE_BYTES, Ordering::SeqCst);

            assert_eq!(
                trigger(&recorder, "fixed", "fixed").await.state,
                TriggerState::Started
            );
            clock.advance(Duration::from_secs(5));
            assert_eq!(
                trigger(&recorder, "fixed", "fixed").await.state,
                TriggerState::Extended
            );
            let fixed = &recorder.status().await["fixed"];
            assert_eq!(
                (fixed.elapsed_sec, fixed.remaining_sec, fixed.frame_count),
                (5.0, 5.0, 2)
            );

            trigger(&recorder, "extend", "extend").await;
            clock.advance(Duration::from_secs(5));
            trigger(&recorder, "extend", "extend").await;
            assert_eq!(recorder.status().await["extend"].remaining_sec, 10.0);

            trigger(&recorder, "capped", "extend_max").await;
            clock.advance(Duration::from_secs(5));
            trigger(&recorder, "capped", "extend_max").await;
            assert_eq!(recorder.status().await["capped"].remaining_sec, 7.0);

            trigger(&recorder, "fourth", "fixed").await;
            assert_eq!(io.spawn_count.load(Ordering::SeqCst), 4);
            assert_eq!(
                recorder
                    .trigger(request("fifth", "fixed"), Bytes::from_static(&[0; 12]))
                    .await
                    .unwrap_err(),
                "Max concurrent recordings reached"
            );
            trigger(&recorder, "fixed", "fixed").await;
            assert_eq!(io.spawn_count.load(Ordering::SeqCst), 4);
            recorder.shutdown().await;
        });
    }

    #[test]
    fn extend_command_precedes_competing_monitor_decision() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (recorder, clock, _io) = fixture(MIN_FREE_BYTES);
            trigger(&recorder, "cam", "extend").await;
            clock.advance(Duration::from_secs(10));

            let (entered_tx, entered_rx) = oneshot::channel();
            let (release_tx, release_rx) = oneshot::channel();
            recorder
                .tx
                .send(RecorderCommand::Hold {
                    entered: entered_tx,
                    release: release_rx,
                })
                .await
                .unwrap();
            entered_rx.await.unwrap();

            let barrier = Arc::new(Barrier::new(3));
            let extend_queued = Arc::new(Notify::new());
            let extend_tx = recorder.tx.clone();
            let extend_barrier = Arc::clone(&barrier);
            let extend_queued_signal = Arc::clone(&extend_queued);
            let (extend_sent_tx, extend_sent_rx) = oneshot::channel();
            let extend_task = tokio::spawn(async move {
                let (reply, result) = oneshot::channel();
                extend_barrier.wait().await;
                extend_tx
                    .send(RecorderCommand::Trigger {
                        request: request("cam", "extend"),
                        frame: Bytes::from_static(&[0; 12]),
                        reply,
                    })
                    .await
                    .unwrap();
                extend_queued_signal.notify_one();
                extend_sent_tx.send(()).unwrap();
                result.await.unwrap()
            });
            let tick_tx = recorder.tx.clone();
            let tick_barrier = Arc::clone(&barrier);
            let tick_queued_signal = Arc::clone(&extend_queued);
            let (tick_sent_tx, tick_sent_rx) = oneshot::channel();
            let tick_task = tokio::spawn(async move {
                let (reply, result) = oneshot::channel();
                tick_barrier.wait().await;
                tick_queued_signal.notified().await;
                tick_tx
                    .send(RecorderCommand::Tick { reply: Some(reply) })
                    .await
                    .unwrap();
                tick_sent_tx.send(()).unwrap();
                result.await.unwrap()
            });
            barrier.wait().await;
            extend_sent_rx.await.unwrap();
            tick_sent_rx.await.unwrap();
            release_tx.send(()).unwrap();
            assert_eq!(
                extend_task.await.unwrap().unwrap().state,
                TriggerState::Extended
            );
            tick_task.await.unwrap();
            assert_eq!(recorder.status().await["cam"].remaining_sec, 10.0);
            recorder.shutdown().await;
        });
    }

    #[test]
    fn monitor_stops_session_at_deadline_on_virtual_wakeup() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let clock = Arc::new(FakeClock::new());
            let io = Arc::new(FakeIo::new(MIN_FREE_BYTES));
            let recorder = Recorder::spawn_with(io, clock.clone(), true);
            trigger(&recorder, "cam", "fixed").await;
            clock.advance(Duration::from_secs(10));
            tokio::time::advance(MONITOR_INTERVAL).await;
            while recorder.status().await.contains_key("cam") {
                tokio::task::yield_now().await;
            }
            recorder.shutdown().await;
        });
    }

    #[test]
    fn stop_shutdown_and_broken_pipe_are_isolated_and_bounded() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (recorder, _clock, io) = fixture(MIN_FREE_BYTES);
            io.hang_sources.lock().unwrap().insert("hung".to_string());
            trigger(&recorder, "hung", "fixed").await;
            assert!(recorder.stop_source("hung").await);
            let hung = io.probes()[0].clone();
            assert!(hung.stdin_closed.load(Ordering::SeqCst));
            assert!(hung.waited.load(Ordering::SeqCst));
            assert!(hung.killed.load(Ordering::SeqCst));

            io.break_next.store(true, Ordering::SeqCst);
            assert!(recorder
                .trigger(request("broken", "fixed"), Bytes::from_static(&[0; 12]))
                .await
                .unwrap_err()
                .contains("pipe failed"));
            trigger(&recorder, "survivor", "fixed").await;
            trigger(&recorder, "second", "fixed").await;
            recorder.shutdown().await;
            assert!(recorder.status().await.is_empty());
            assert!(io.probes().iter().all(|probe| {
                probe.stdin_closed.load(Ordering::SeqCst) && probe.waited.load(Ordering::SeqCst)
            }));
        });
    }

    #[test]
    fn status_shape_values_and_safe_filename_are_fixed() {
        run_bounded_test(TEST_TIMEOUT, async {
            for source_id in ["../x", "a/b\\c", "/tmp/absolute", r"C:\tmp\x"] {
                let filename = recording_filename("2026-08-13_142536", source_id);
                assert!(filename.starts_with("2026-08-13_142536_"));
                assert!(filename.ends_with(".mp4"));
                assert!(!filename.contains(".."));
                assert!(!filename.contains('/'));
                assert!(!filename.contains('\\'));
                assert_eq!(Path::new(&filename).components().count(), 1);
            }

            let (recorder, clock, io) = fixture(MIN_FREE_BYTES);
            assert_eq!(
                serde_json::to_value(recorder.status().await).unwrap(),
                serde_json::json!({})
            );
            trigger(&recorder, "../x", "extend").await;
            clock.advance(Duration::from_millis(2_500));
            let value = serde_json::to_value(recorder.status().await).unwrap();
            let session = &value["../x"];
            assert_eq!(session.as_object().unwrap().len(), 6);
            assert_eq!(session["source_id"], "../x");
            assert_eq!(session["extend_mode"], "extend");
            assert_eq!(session["elapsed_sec"], 2.5);
            assert_eq!(session["remaining_sec"], 7.5);
            assert_eq!(session["frame_count"], 1);
            let spawned_path = io.probes.lock().unwrap()[0].0.clone();
            assert_eq!(spawned_path.parent(), Some(Path::new("/recordings")));
            assert_eq!(
                spawned_path.file_name().unwrap().to_string_lossy(),
                "2026-08-13_142536___x.mp4"
            );
            recorder.shutdown().await;
        });
    }

    #[test]
    fn graceful_stop_writes_probeable_mp4() {
        run_bounded_test(TEST_TIMEOUT, async {
            assert!(StdCommand::new("ffmpeg")
                .arg("-version")
                .output()
                .unwrap()
                .status
                .success());
            assert!(StdCommand::new("ffprobe")
                .arg("-version")
                .output()
                .unwrap()
                .status
                .success());
            let directory = TempDir::new().unwrap();
            let recorder =
                Recorder::spawn_with(Arc::new(SystemIo), Arc::new(SystemClock::default()), false);
            let mut real = request("probe", "fixed");
            real.save_dir = directory.path().to_path_buf();
            real.fps = 1.0;
            let result = recorder
                .trigger(
                    real,
                    Bytes::from_static(&[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                )
                .await
                .unwrap();
            assert!(recorder.stop_source("probe").await);
            let output = StdCommand::new("ffprobe")
                .args([
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name",
                    "-of",
                    "default=nw=1:nk=1",
                ])
                .arg(&result.path)
                .output()
                .unwrap();
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            assert!(String::from_utf8_lossy(&output.stdout).contains("mp4"));
            recorder.shutdown().await;
        });
    }
}
