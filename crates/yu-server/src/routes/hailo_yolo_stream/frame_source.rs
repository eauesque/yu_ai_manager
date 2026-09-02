use std::{
    ffi::OsString,
    io,
    process::Stdio,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender, TryRecvError},
        Arc, Condvar, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use thiserror::Error;
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, BufReader},
    process::{Child, ChildStderr, ChildStdout, Command},
    runtime::Handle,
    sync::mpsc as tokio_mpsc,
    task::JoinHandle as TokioJoinHandle,
    time::timeout,
};

use super::input::{ffmpeg_input_args, SourceKind};

pub(crate) const FRAME_STALL_TIMEOUT: Duration = Duration::from_secs(5);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const FFPROBE_TIMEOUT: Duration = Duration::from_secs(5);
const STOP_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_FAILURES: usize = 6;
const RETRY_BACKOFFS: [Duration; MAX_FAILURES] = [
    Duration::from_secs(1),
    Duration::from_secs(2),
    Duration::from_secs(4),
    Duration::from_secs(8),
    Duration::from_secs(16),
    Duration::from_secs(30),
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Frame {
    pub(crate) width: u32,
    pub(crate) height: u32,
    pub(crate) bytes: Vec<u8>,
}

#[derive(Debug, Clone, Error, PartialEq, Eq)]
pub(crate) enum SourceError {
    #[error("source was interrupted")]
    Interrupted,
    #[error("source configuration is invalid")]
    InvalidConfiguration,
    #[error("frame dimensions are invalid")]
    InvalidDimensions,
    #[error("ffprobe could not determine frame dimensions")]
    ProbeFailed,
    #[error("ffprobe timed out")]
    ProbeTimeout,
    #[error("failed to start source process: {0}")]
    Spawn(io::ErrorKind),
    #[error("frame read failed: {0}")]
    Read(io::ErrorKind),
    #[error("source process wait failed: {0}")]
    Wait(io::ErrorKind),
    #[error("source process did not stop before the deadline")]
    StopTimeout,
    #[error("source process exited unsuccessfully ({0:?})")]
    ProcessExit(Option<i32>),
    #[error("source reader thread panicked")]
    ReaderPanicked,
    #[error("stderr drain thread panicked")]
    DrainPanicked,
    #[error("source stalled")]
    Stalled,
    #[error("source failed after six consecutive attempts")]
    RetriesExhausted,
    #[error("file stream ended")]
    FileEnded,
}

pub(crate) trait FrameSource: Send {
    fn next_frame(&mut self) -> Result<Option<Frame>, SourceError>;
}

enum SyntheticMode {
    Finite { next: usize, count: usize },
    Stall(Arc<(Mutex<bool>, Condvar)>),
}

pub(crate) struct SyntheticSource {
    width: u32,
    height: u32,
    mode: SyntheticMode,
}

impl SyntheticSource {
    pub(crate) fn finite(width: u32, height: u32, count: usize) -> Self {
        Self {
            width,
            height,
            mode: SyntheticMode::Finite { next: 0, count },
        }
    }

    fn stall() -> (Self, SyntheticInterrupt) {
        let state = Arc::new((Mutex::new(false), Condvar::new()));
        (
            Self {
                width: 1,
                height: 1,
                mode: SyntheticMode::Stall(Arc::clone(&state)),
            },
            SyntheticInterrupt { state },
        )
    }
}

impl FrameSource for SyntheticSource {
    // The synthetic frame's fill byte is derived from the frame index purely to
    // make successive frames visually distinct; wrapping past 255 is the point
    // of `wrapping_mul` and carries no meaning that could be lost.
    #[allow(clippy::cast_possible_truncation)]
    fn next_frame(&mut self) -> Result<Option<Frame>, SourceError> {
        match &mut self.mode {
            SyntheticMode::Finite { next, count } => {
                if *next >= *count {
                    return Ok(None);
                }
                let frame_len = frame_len(self.width, self.height)?;
                let index = *next;
                let base = (index as u8).wrapping_mul(17);
                let mut bytes = vec![base; frame_len];
                for pixel in bytes.as_chunks_mut::<3>().0 {
                    pixel[1] = base.wrapping_add(1);
                    pixel[2] = base.wrapping_add(2);
                }
                let x = index % self.width as usize;
                for y in 0..self.height.min(2) as usize {
                    let offset = (y * self.width as usize + x) * 3;
                    bytes[offset..offset + 3].copy_from_slice(&[0, 255, 255]);
                }
                *next += 1;
                Ok(Some(Frame {
                    width: self.width,
                    height: self.height,
                    bytes,
                }))
            }
            SyntheticMode::Stall(state) => {
                let (lock, wake) = &**state;
                let mut interrupted = lock.lock().unwrap_or_else(|error| error.into_inner());
                while !*interrupted {
                    interrupted = wake
                        .wait(interrupted)
                        .unwrap_or_else(|error| error.into_inner());
                }
                Err(SourceError::Interrupted)
            }
        }
    }
}

struct SyntheticInterrupt {
    state: Arc<(Mutex<bool>, Condvar)>,
}

impl SyntheticInterrupt {
    fn interrupt(&self) {
        let (lock, wake) = &*self.state;
        *lock.lock().unwrap_or_else(|error| error.into_inner()) = true;
        wake.notify_all();
    }
}

pub(crate) struct FfmpegSource {
    stdout: BufReader<ChildStdout>,
    width: u32,
    height: u32,
    frame_len: usize,
    runtime: Handle,
}

impl FfmpegSource {
    fn new(
        stdout: ChildStdout,
        width: u32,
        height: u32,
        runtime: Handle,
    ) -> Result<Self, SourceError> {
        Ok(Self {
            stdout: BufReader::new(stdout),
            width,
            height,
            frame_len: frame_len(width, height)?,
            runtime,
        })
    }
}

impl FrameSource for FfmpegSource {
    fn next_frame(&mut self) -> Result<Option<Frame>, SourceError> {
        let runtime = self.runtime.clone();
        let stdout = &mut self.stdout;
        let at_eof = runtime
            .block_on(async { stdout.fill_buf().await.map(|bytes| bytes.is_empty()) })
            .map_err(|error| SourceError::Read(error.kind()))?;
        if at_eof {
            return Ok(None);
        }

        let mut bytes = vec![0; self.frame_len];
        runtime
            .block_on(async { stdout.read_exact(&mut bytes).await })
            .map_err(|error| SourceError::Read(error.kind()))?;
        Ok(Some(Frame {
            width: self.width,
            height: self.height,
            bytes,
        }))
    }
}

fn frame_len(width: u32, height: u32) -> Result<usize, SourceError> {
    let width = usize::try_from(width).map_err(|_| SourceError::InvalidDimensions)?;
    let height = usize::try_from(height).map_err(|_| SourceError::InvalidDimensions)?;
    width
        .checked_mul(height)
        .and_then(|pixels| pixels.checked_mul(3))
        .filter(|length| *length > 0)
        .ok_or(SourceError::InvalidDimensions)
}

#[derive(Clone, Copy)]
enum EofPolicy {
    Ended,
    FileError,
    Retry,
}

pub(crate) struct FfmpegFactory {
    input_args: Vec<OsString>,
    eof_policy: EofPolicy,
}

impl FfmpegFactory {
    pub(crate) fn new(source: &SourceKind) -> Result<Self, SourceError> {
        let input_args =
            ffmpeg_input_args(source).map_err(|_| SourceError::InvalidConfiguration)?;
        let eof_policy = match source {
            SourceKind::LocalFile(_) => EofPolicy::FileError,
            SourceKind::Remote(_) | SourceKind::UsbIndex(_) => EofPolicy::Retry,
        };
        Ok(Self {
            input_args,
            eof_policy,
        })
    }

    #[cfg(test)]
    fn lavfi(filter: &str) -> Self {
        Self {
            input_args: ["-f", "lavfi", "-i"]
                .into_iter()
                .map(OsString::from)
                .chain([OsString::from(filter)])
                .collect(),
            eof_policy: EofPolicy::Ended,
        }
    }
}

trait AttemptFactory: Send + 'static {
    fn connect(&mut self, runtime: &Handle) -> Result<SourceAttempt, SourceError>;
    fn eof_policy(&self) -> EofPolicy;
}

impl AttemptFactory for FfmpegFactory {
    fn connect(&mut self, runtime: &Handle) -> Result<SourceAttempt, SourceError> {
        let (width, height) = probe_dimensions(runtime, &self.input_args)?;
        let mut command = Command::new("/usr/bin/ffmpeg");
        command
            .args(["-hide_banner", "-loglevel", "warning", "-nostdin"])
            .args(&self.input_args)
            .args([
                "-an", "-sn", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
            ]);
        spawn_ffmpeg_attempt(runtime, command, width, height)
    }

    fn eof_policy(&self) -> EofPolicy {
        self.eof_policy
    }
}

fn probe_dimensions(runtime: &Handle, input_args: &[OsString]) -> Result<(u32, u32), SourceError> {
    let mut command = Command::new("/usr/bin/ffprobe");
    command
        .args(["-v", "error"])
        .args(input_args)
        .args([
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    let output = runtime.block_on(async {
        let mut child = command
            .spawn()
            .map_err(|error| SourceError::Spawn(error.kind()))?;
        let mut stdout = child.stdout.take().ok_or(SourceError::ProbeFailed)?;
        let mut stderr = child.stderr.take().ok_or(SourceError::ProbeFailed)?;
        let stdout_task = tokio::spawn(async move {
            let mut bytes = Vec::new();
            stdout
                .read_to_end(&mut bytes)
                .await
                .map_err(|error| SourceError::Read(error.kind()))?;
            Ok::<_, SourceError>(bytes)
        });
        let stderr_task = tokio::spawn(async move {
            tokio::io::copy(&mut stderr, &mut tokio::io::sink())
                .await
                .map_err(|error| SourceError::Read(error.kind()))
        });

        let status = match timeout(FFPROBE_TIMEOUT, child.wait()).await {
            Ok(result) => result.map_err(|error| SourceError::Wait(error.kind()))?,
            Err(_) => {
                child
                    .start_kill()
                    .map_err(|error| SourceError::Wait(error.kind()))?;
                let _ = timeout(STOP_TIMEOUT, child.wait()).await;
                return Err(SourceError::ProbeTimeout);
            }
        };
        let bytes = stdout_task.await.map_err(|_| SourceError::ProbeFailed)??;
        stderr_task.await.map_err(|_| SourceError::ProbeFailed)??;
        status
            .success()
            .then_some(bytes)
            .ok_or(SourceError::ProbeFailed)
    })?;

    let dimensions = std::str::from_utf8(&output)
        .ok()
        .and_then(|value| value.lines().find(|line| !line.trim().is_empty()))
        .and_then(|line| line.trim().split_once('x'))
        .and_then(|(width, height)| Some((width.parse().ok()?, height.parse().ok()?)));
    match dimensions {
        Some((width, height)) if frame_len(width, height).is_ok() => Ok((width, height)),
        _ => Err(SourceError::ProbeFailed),
    }
}

fn spawn_ffmpeg_attempt(
    runtime: &Handle,
    mut command: Command,
    width: u32,
    height: u32,
) -> Result<SourceAttempt, SourceError> {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let mut child = command
        .spawn()
        .map_err(|error| SourceError::Spawn(error.kind()))?;
    let pid = child.id();
    let stdout = child
        .stdout
        .take()
        .ok_or(SourceError::InvalidConfiguration)?;
    let stderr = child
        .stderr
        .take()
        .ok_or(SourceError::InvalidConfiguration)?;
    let stderr_thread = spawn_stderr_drain(runtime.clone(), stderr);
    let source = FfmpegSource::new(stdout, width, height, runtime.clone())?;
    Ok(SourceAttempt {
        source: Box::new(source),
        control: Box::new(FfmpegControl {
            child: Some(child),
            stderr_thread: Some(stderr_thread),
            runtime: runtime.clone(),
        }),
        pid,
        width,
        height,
    })
}

fn spawn_stderr_drain(
    runtime: Handle,
    mut stderr: ChildStderr,
) -> JoinHandle<Result<(), SourceError>> {
    thread::spawn(move || {
        runtime
            .block_on(async { tokio::io::copy(&mut stderr, &mut tokio::io::sink()).await })
            .map(|_| ())
            .map_err(|error| SourceError::Read(error.kind()))
    })
}

trait AttemptControl: Send {
    fn shutdown(&mut self, kill: bool) -> Result<(), SourceError>;
}

struct FfmpegControl {
    child: Option<Child>,
    stderr_thread: Option<JoinHandle<Result<(), SourceError>>>,
    runtime: Handle,
}

impl AttemptControl for FfmpegControl {
    fn shutdown(&mut self, kill: bool) -> Result<(), SourceError> {
        let mut child = self
            .child
            .take()
            .ok_or(SourceError::Wait(io::ErrorKind::Other))?;
        drop(child.stdin.take());
        let status = self.runtime.block_on(async {
            if kill {
                child
                    .start_kill()
                    .map_err(|error| SourceError::Wait(error.kind()))?;
            }
            match timeout(STOP_TIMEOUT, child.wait()).await {
                Ok(result) => result.map_err(|error| SourceError::Wait(error.kind())),
                Err(_) if !kill => {
                    child
                        .start_kill()
                        .map_err(|error| SourceError::Wait(error.kind()))?;
                    timeout(STOP_TIMEOUT, child.wait())
                        .await
                        .map_err(|_| SourceError::StopTimeout)?
                        .map_err(|error| SourceError::Wait(error.kind()))
                }
                Err(_) => Err(SourceError::StopTimeout),
            }
        })?;
        let drain_result = self
            .stderr_thread
            .take()
            .ok_or(SourceError::DrainPanicked)?
            .join()
            .map_err(|_| SourceError::DrainPanicked)?;
        drain_result?;
        if !kill && !status.success() {
            return Err(SourceError::ProcessExit(status.code()));
        }
        Ok(())
    }
}

struct SourceAttempt {
    source: Box<dyn FrameSource>,
    control: Box<dyn AttemptControl>,
    pid: Option<u32>,
    width: u32,
    height: u32,
}

enum ReaderEvent {
    Frame(Frame),
    Eof,
    Error(SourceError),
}

pub(crate) trait Clock: Send + Sync {
    fn now(&self) -> Duration;
    fn token(&self) -> u64;
    fn notify(&self);
    fn wait_until(&self, deadline: Duration, token: u64);
}

pub(crate) struct SystemClock {
    origin: Instant,
    state: Mutex<u64>,
    wake: Condvar,
}

impl Default for SystemClock {
    fn default() -> Self {
        Self {
            origin: Instant::now(),
            state: Mutex::new(0),
            wake: Condvar::new(),
        }
    }
}

impl Clock for SystemClock {
    fn now(&self) -> Duration {
        self.origin.elapsed()
    }

    fn token(&self) -> u64 {
        *self.state.lock().unwrap_or_else(|error| error.into_inner())
    }

    fn notify(&self) {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        *state = state.wrapping_add(1);
        self.wake.notify_all();
    }

    fn wait_until(&self, deadline: Duration, token: u64) {
        let state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        if *state == token {
            let remaining = deadline.saturating_sub(self.now());
            drop(
                self.wake
                    .wait_timeout(state, remaining)
                    .unwrap_or_else(|error| error.into_inner()),
            );
        }
    }
}

#[derive(Debug)]
pub(crate) enum SupervisorEvent {
    Connected {
        pid: Option<u32>,
        width: u32,
        height: u32,
    },
    Frame(Frame),
    Reconnecting {
        failures: usize,
        backoff: Duration,
    },
    Ended,
    Stopped,
    Error(SourceError),
}

pub(crate) struct SupervisorHandle {
    pub(crate) events: tokio_mpsc::UnboundedReceiver<SupervisorEvent>,
    stop: Arc<AtomicBool>,
    clock: Arc<dyn Clock>,
    task: TokioJoinHandle<Result<(), SourceError>>,
}

impl SupervisorHandle {
    pub(crate) fn request_stop(&self) {
        self.stop.store(true, Ordering::Release);
        self.clock.notify();
    }

    pub(crate) async fn wait(self) -> Result<(), SourceError> {
        self.task.await.map_err(|_| SourceError::ReaderPanicked)?
    }

    pub(crate) async fn stop(self) -> Result<(), SourceError> {
        self.request_stop();
        self.wait().await
    }
}

pub(crate) fn spawn_ffmpeg_supervisor(factory: FfmpegFactory) -> SupervisorHandle {
    spawn_supervisor(Box::new(factory), Arc::new(SystemClock::default()))
}

fn spawn_supervisor(factory: Box<dyn AttemptFactory>, clock: Arc<dyn Clock>) -> SupervisorHandle {
    let stop = Arc::new(AtomicBool::new(false));
    let (events_tx, events) = tokio_mpsc::unbounded_channel();
    let runtime = Handle::current();
    let task_stop = Arc::clone(&stop);
    let task_clock = Arc::clone(&clock);
    let dispatcher = tracing::dispatcher::get_default(Clone::clone);
    let task = tokio::task::spawn_blocking(move || {
        tracing::dispatcher::with_default(&dispatcher, || {
            run_supervisor(factory, task_clock, task_stop, events_tx, runtime)
        })
    });
    SupervisorHandle {
        events,
        stop,
        clock,
        task,
    }
}

fn run_supervisor(
    mut factory: Box<dyn AttemptFactory>,
    clock: Arc<dyn Clock>,
    stop: Arc<AtomicBool>,
    events: tokio_mpsc::UnboundedSender<SupervisorEvent>,
    runtime: Handle,
) -> Result<(), SourceError> {
    let mut failures = 0;
    loop {
        if stop.load(Ordering::Acquire) {
            let _ = events.send(SupervisorEvent::Stopped);
            return Ok(());
        }

        let attempt = match factory.connect(&runtime) {
            Ok(attempt) => attempt,
            Err(error) => {
                if matches!(factory.eof_policy(), EofPolicy::Retry) {
                    retry_or_finish(&clock, &stop, &events, &mut failures, error)?;
                    continue;
                }
                let _ = events.send(SupervisorEvent::Error(error.clone()));
                return Err(error);
            }
        };
        let connected_at = clock.now();
        let _ = events.send(SupervisorEvent::Connected {
            pid: attempt.pid,
            width: attempt.width,
            height: attempt.height,
        });

        match run_attempt(attempt, connected_at, &clock, &stop, &events, &mut failures)? {
            AttemptEnd::Stopped => {
                let _ = events.send(SupervisorEvent::Stopped);
                return Ok(());
            }
            AttemptEnd::Eof => match factory.eof_policy() {
                EofPolicy::Ended => {
                    let _ = events.send(SupervisorEvent::Ended);
                    return Ok(());
                }
                EofPolicy::FileError => {
                    let error = SourceError::FileEnded;
                    let _ = events.send(SupervisorEvent::Error(error.clone()));
                    return Err(error);
                }
                EofPolicy::Retry => retry_or_finish(
                    &clock,
                    &stop,
                    &events,
                    &mut failures,
                    SourceError::Read(io::ErrorKind::UnexpectedEof),
                )?,
            },
            AttemptEnd::Failure(error) => {
                retry_or_finish(&clock, &stop, &events, &mut failures, error)?
            }
        }
    }
}

enum AttemptEnd {
    Stopped,
    Eof,
    Failure(SourceError),
}

fn run_attempt(
    attempt: SourceAttempt,
    connected_at: Duration,
    clock: &Arc<dyn Clock>,
    stop: &Arc<AtomicBool>,
    events: &tokio_mpsc::UnboundedSender<SupervisorEvent>,
    failures: &mut usize,
) -> Result<AttemptEnd, SourceError> {
    let SourceAttempt {
        mut source,
        mut control,
        ..
    } = attempt;
    let (reader_tx, mut reader_rx) = mpsc::sync_channel(1);
    let reader_clock = Arc::clone(clock);
    let reader = thread::spawn(move || read_frames(&mut *source, reader_tx, &reader_clock));
    let mut last_frame = None;

    loop {
        let token = clock.token();
        if stop.load(Ordering::Acquire) {
            drop(reader_rx);
            control.shutdown(true)?;
            reader.join().map_err(|_| SourceError::ReaderPanicked)?;
            return Ok(AttemptEnd::Stopped);
        }

        match reader_rx.try_recv() {
            Ok(ReaderEvent::Frame(frame)) => {
                last_frame = Some(clock.now());
                *failures = 0;
                if events.send(SupervisorEvent::Frame(frame)).is_err() {
                    drop(reader_rx);
                    control.shutdown(true)?;
                    reader.join().map_err(|_| SourceError::ReaderPanicked)?;
                    return Ok(AttemptEnd::Stopped);
                }
                continue;
            }
            Ok(ReaderEvent::Eof) => {
                drop(reader_rx);
                let shutdown = control.shutdown(false);
                reader.join().map_err(|_| SourceError::ReaderPanicked)?;
                shutdown?;
                return Ok(AttemptEnd::Eof);
            }
            Ok(ReaderEvent::Error(error)) => {
                drop(reader_rx);
                let shutdown = control.shutdown(true);
                reader.join().map_err(|_| SourceError::ReaderPanicked)?;
                shutdown?;
                return Ok(AttemptEnd::Failure(error));
            }
            Err(TryRecvError::Disconnected) => {
                drop(reader_rx);
                let shutdown = control.shutdown(true);
                reader.join().map_err(|_| SourceError::ReaderPanicked)?;
                shutdown?;
                return Ok(AttemptEnd::Failure(SourceError::Read(
                    io::ErrorKind::BrokenPipe,
                )));
            }
            Err(TryRecvError::Empty) => {}
        }

        let deadline = last_frame
            .map(|last| last + FRAME_STALL_TIMEOUT)
            .unwrap_or(connected_at + CONNECT_TIMEOUT);
        if clock.now() >= deadline {
            drop(reader_rx);
            let shutdown = control.shutdown(true);
            reader.join().map_err(|_| SourceError::ReaderPanicked)?;
            shutdown?;
            return Ok(AttemptEnd::Failure(SourceError::Stalled));
        }
        clock.wait_until(deadline, token);
    }
}

fn read_frames(
    source: &mut dyn FrameSource,
    sender: SyncSender<ReaderEvent>,
    clock: &Arc<dyn Clock>,
) {
    loop {
        let event = match source.next_frame() {
            Ok(Some(frame)) => ReaderEvent::Frame(frame),
            Ok(None) => ReaderEvent::Eof,
            Err(error) => ReaderEvent::Error(error),
        };
        let finished = !matches!(event, ReaderEvent::Frame(_));
        if sender.send(event).is_err() {
            return;
        }
        clock.notify();
        if finished {
            return;
        }
    }
}

fn retry_or_finish(
    clock: &Arc<dyn Clock>,
    stop: &Arc<AtomicBool>,
    events: &tokio_mpsc::UnboundedSender<SupervisorEvent>,
    failures: &mut usize,
    _cause: SourceError,
) -> Result<(), SourceError> {
    *failures += 1;
    if *failures >= MAX_FAILURES {
        let error = SourceError::RetriesExhausted;
        let _ = events.send(SupervisorEvent::Error(error.clone()));
        return Err(error);
    }
    let backoff = RETRY_BACKOFFS[*failures - 1];
    let deadline = clock.now() + backoff;
    let _ = events.send(SupervisorEvent::Reconnecting {
        failures: *failures,
        backoff,
    });
    while clock.now() < deadline {
        if stop.load(Ordering::Acquire) {
            return Ok(());
        }
        let token = clock.token();
        if clock.now() < deadline {
            clock.wait_until(deadline, token);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{
        io::Write,
        path::Path,
        sync::atomic::{AtomicUsize, Ordering},
    };

    use tracing_subscriber::fmt::MakeWriter;

    use super::super::run_bounded_test;
    use super::*;

    const TEST_TIMEOUT: Duration = Duration::from_secs(30);

    #[derive(Default)]
    struct ManualClock {
        state: Mutex<(Duration, u64)>,
        wake: Condvar,
    }

    impl ManualClock {
        fn advance(&self, duration: Duration) {
            let mut state = self.state.lock().unwrap();
            state.0 += duration;
            state.1 = state.1.wrapping_add(1);
            self.wake.notify_all();
        }
    }

    impl Clock for ManualClock {
        fn now(&self) -> Duration {
            self.state.lock().unwrap().0
        }

        fn token(&self) -> u64 {
            self.state.lock().unwrap().1
        }

        fn notify(&self) {
            let mut state = self.state.lock().unwrap();
            state.1 = state.1.wrapping_add(1);
            self.wake.notify_all();
        }

        fn wait_until(&self, deadline: Duration, token: u64) {
            let mut state = self.state.lock().unwrap();
            while state.0 < deadline && state.1 == token {
                state = self.wake.wait(state).unwrap();
            }
        }
    }

    struct SyntheticControl {
        interrupt: SyntheticInterrupt,
        interruptions: Arc<AtomicUsize>,
    }

    impl AttemptControl for SyntheticControl {
        fn shutdown(&mut self, kill: bool) -> Result<(), SourceError> {
            if kill {
                self.interruptions.fetch_add(1, Ordering::Relaxed);
                self.interrupt.interrupt();
            }
            Ok(())
        }
    }

    struct StallFactory {
        interruptions: Arc<AtomicUsize>,
    }

    impl AttemptFactory for StallFactory {
        fn connect(&mut self, _runtime: &Handle) -> Result<SourceAttempt, SourceError> {
            let (source, interrupt) = SyntheticSource::stall();
            Ok(SourceAttempt {
                source: Box::new(source),
                control: Box::new(SyntheticControl {
                    interrupt,
                    interruptions: Arc::clone(&self.interruptions),
                }),
                pid: None,
                width: 1,
                height: 1,
            })
        }

        fn eof_policy(&self) -> EofPolicy {
            EofPolicy::Retry
        }
    }

    struct FixtureFactory {
        secret: String,
    }

    impl AttemptFactory for FixtureFactory {
        fn connect(&mut self, runtime: &Handle) -> Result<SourceAttempt, SourceError> {
            let script = "dd if=/dev/zero bs=65536 count=32 2>/dev/null >&2; printf '%s' \"$1\" >&2; printf '\\001\\002\\003\\004\\005\\006\\007\\010\\011\\012\\013\\014'";
            let mut command = Command::new("/bin/sh");
            command.args(["-c", script, "fixture", &self.secret]);
            spawn_ffmpeg_attempt(runtime, command, 2, 2)
        }

        fn eof_policy(&self) -> EofPolicy {
            EofPolicy::Ended
        }
    }

    #[derive(Clone, Default)]
    struct CapturedLogs(Arc<Mutex<Vec<u8>>>);

    struct CapturedWriter(Arc<Mutex<Vec<u8>>>);

    impl<'a> MakeWriter<'a> for CapturedLogs {
        type Writer = CapturedWriter;

        fn make_writer(&'a self) -> Self::Writer {
            CapturedWriter(Arc::clone(&self.0))
        }
    }

    impl Write for CapturedWriter {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    async fn ffmpeg_available() -> bool {
        Command::new("/usr/bin/ffmpeg")
            .arg("-version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await
            .is_ok_and(|status| status.success())
            && Command::new("/usr/bin/ffprobe")
                .arg("-version")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .await
                .is_ok_and(|status| status.success())
    }

    #[test]
    fn synthetic_source_returns_deterministic_frames_then_eof() {
        let mut source = SyntheticSource::finite(4, 3, 2);
        let first = source.next_frame().unwrap().unwrap();
        let second = source.next_frame().unwrap().unwrap();

        assert_eq!((first.width, first.height, first.bytes.len()), (4, 3, 36));
        assert_eq!(&first.bytes[0..3], &[0, 255, 255]);
        assert_eq!(&first.bytes[3..6], &[0, 1, 2]);
        assert_eq!(&second.bytes[0..3], &[17, 18, 19]);
        assert_eq!(&second.bytes[3..6], &[0, 255, 255]);
        assert_eq!(source.next_frame().unwrap(), None);
    }

    #[test]
    fn real_ffmpeg_reads_exact_frames_and_reaps_clean_eof() {
        run_bounded_test(TEST_TIMEOUT, async move {
            if !ffmpeg_available().await {
                return;
            }
            let factory = FfmpegFactory::lavfi("testsrc=size=320x240:rate=3:duration=1");
            let mut supervisor = spawn_ffmpeg_supervisor(factory);
            let mut pid = None;
            let mut frames = Vec::new();
            while let Some(event) = supervisor.events.recv().await {
                match event {
                    SupervisorEvent::Connected {
                        pid: child_pid,
                        width,
                        height,
                    } => {
                        pid = child_pid;
                        assert_eq!((width, height), (320, 240));
                    }
                    SupervisorEvent::Frame(frame) => frames.push(frame),
                    SupervisorEvent::Ended => break,
                    SupervisorEvent::Error(error) => panic!("unexpected source error: {error}"),
                    SupervisorEvent::Reconnecting { .. } | SupervisorEvent::Stopped => {}
                }
            }
            supervisor.wait().await.unwrap();

            assert_eq!(frames.len(), 3);
            assert!(frames.iter().all(|frame| frame.width == 320
                && frame.height == 240
                && frame.bytes.len() == 230_400));
            #[cfg(target_os = "linux")]
            assert!(!Path::new(&format!("/proc/{}", pid.unwrap())).exists());
            // Only the Linux assertion reads `pid`; elsewhere it is deliberately unused.
            #[cfg(not(target_os = "linux"))]
            let _ = pid;
        });
    }

    #[test]
    fn real_ffmpeg_stop_kills_and_reaps_child() {
        run_bounded_test(TEST_TIMEOUT, async move {
            if !ffmpeg_available().await {
                return;
            }
            let factory = FfmpegFactory::lavfi("testsrc=size=64x48:rate=30");
            let mut supervisor = spawn_ffmpeg_supervisor(factory);
            let pid = loop {
                if let Some(SupervisorEvent::Connected { pid: Some(pid), .. }) =
                    supervisor.events.recv().await
                {
                    break pid;
                }
            };
            supervisor.stop().await.unwrap();
            #[cfg(target_os = "linux")]
            assert!(!Path::new(&format!("/proc/{pid}")).exists());
        });
    }

    #[test]
    fn injected_clock_stall_interrupts_and_errors_after_six_failures() {
        run_bounded_test(TEST_TIMEOUT, async move {
            let clock = Arc::new(ManualClock::default());
            let interruptions = Arc::new(AtomicUsize::new(0));
            let mut supervisor = spawn_supervisor(
                Box::new(StallFactory {
                    interruptions: Arc::clone(&interruptions),
                }),
                clock.clone(),
            );

            for failure in 1..=MAX_FAILURES {
                assert!(matches!(
                    supervisor.events.recv().await,
                    Some(SupervisorEvent::Connected { .. })
                ));
                clock.advance(FRAME_STALL_TIMEOUT);
                if failure < MAX_FAILURES {
                    let event = supervisor.events.recv().await.unwrap();
                    assert!(matches!(
                        event,
                        SupervisorEvent::Reconnecting {
                            failures,
                            backoff
                        } if failures == failure && backoff == RETRY_BACKOFFS[failure - 1]
                    ));
                    clock.advance(RETRY_BACKOFFS[failure - 1]);
                }
            }
            assert!(matches!(
                supervisor.events.recv().await,
                Some(SupervisorEvent::Error(SourceError::RetriesExhausted))
            ));
            assert_eq!(supervisor.wait().await, Err(SourceError::RetriesExhausted));
            assert_eq!(interruptions.load(Ordering::Relaxed), MAX_FAILURES);
        });
    }

    #[test]
    fn stderr_drain_discards_credentials_without_log_or_error_exposure() {
        run_bounded_test(TEST_TIMEOUT, async move {
            let source_url = "rtsp://camera-user:camera-password@example.test/live";
            let logs = CapturedLogs::default();
            let subscriber = tracing_subscriber::fmt().with_writer(logs.clone()).finish();
            let _guard = tracing::subscriber::set_default(subscriber);
            let mut supervisor = spawn_supervisor(
                Box::new(FixtureFactory {
                    secret: source_url.to_string(),
                }),
                Arc::new(SystemClock::default()),
            );
            let mut diagnostics = Vec::new();
            while let Some(event) = supervisor.events.recv().await {
                diagnostics.push(format!("{event:?}"));
                if matches!(event, SupervisorEvent::Ended | SupervisorEvent::Error(_)) {
                    break;
                }
            }
            supervisor.wait().await.unwrap();

            let logs = String::from_utf8(logs.0.lock().unwrap().clone()).unwrap();
            let diagnostics = diagnostics.join("\n");
            for secret in [source_url, "camera-user", "camera-password"] {
                assert!(!logs.contains(secret));
                assert!(!diagnostics.contains(secret));
            }
        });
    }
}
