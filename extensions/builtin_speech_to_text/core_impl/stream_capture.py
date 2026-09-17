"""FFmpeg pipe-based audio capture for real-time stream transcription."""

import contextlib
import logging
import subprocess
import threading

import numpy as np

logger = logging.getLogger(__name__)

# Valid states
_STATES = ("stopped", "running", "reconnecting", "error")

_MAX_RECONNECT_ATTEMPTS = 10
_MAX_RECONNECT_DELAY = 30  # seconds


class StreamCapture:
    """Spawn FFmpeg to read audio from RTSP/RTSPS and output PCM via pipe.

    Output format: s16le, mono, 16 kHz (configurable sample_rate).
    """

    def __init__(self, source_url: str, sample_rate: int = 16000) -> None:
        self.source_url = source_url
        self.sample_rate = sample_rate

        self._state: str = "stopped"
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

        # Reconnect bookkeeping (managed externally via try_reconnect)
        self._reconnect_count: int = 0

    # -- Properties -----------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == "running"

    @property
    def reconnect_delay(self) -> float:
        """Exponential back-off delay (capped at _MAX_RECONNECT_DELAY)."""
        return min(2 ** self._reconnect_count, _MAX_RECONNECT_DELAY)

    # -- Public API -----------------------------------------------------------

    def start(self) -> None:
        """Spawn the FFmpeg subprocess."""
        with self._lock:
            if self._process is not None:
                return
            cmd = self._build_ffmpeg_cmd()
            logger.info("StreamCapture starting: %s", " ".join(cmd))
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._state = "running"
                self._reconnect_count = 0
            except FileNotFoundError:
                logger.error("ffmpeg not found on PATH")
                self._state = "error"
            except Exception:
                logger.exception("Failed to start FFmpeg")
                self._state = "error"

    def stop(self) -> None:
        """Terminate the FFmpeg process and clean up."""
        with self._lock:
            self._terminate_process()
            self._state = "stopped"
            self._reconnect_count = 0

    def read_chunk(self, duration_sec: float) -> np.ndarray | None:
        """Read *duration_sec* seconds of PCM audio from the FFmpeg pipe.

        Returns an int16 numpy array, or None if the stream is not running
        or the pipe yields no data.
        """
        # Snapshot process reference under lock, then release before blocking read.
        with self._lock:
            if self._state != "running" or self._process is None:
                return None
            process = self._process

        byte_count = int(self.sample_rate * duration_sec * 2)  # 2 bytes per int16 sample
        try:
            raw = process.stdout.read(byte_count)  # type: ignore[union-attr]
        except Exception:
            logger.exception("Error reading from FFmpeg pipe")
            with self._lock:
                self._handle_disconnect()
            return None

        if not raw:
            with self._lock:
                self._handle_disconnect()
            return None

        return np.frombuffer(raw, dtype=np.int16)

    def try_reconnect(self) -> bool:
        """Attempt to restart FFmpeg.  Returns True on success."""
        with self._lock:
            if self._reconnect_count >= _MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    "Max reconnect attempts (%d) reached", _MAX_RECONNECT_ATTEMPTS
                )
                self._state = "error"
                return False

            self._terminate_process()
            self._reconnect_count += 1
            logger.info(
                "Reconnect attempt %d/%d for %s",
                self._reconnect_count,
                _MAX_RECONNECT_ATTEMPTS,
                self.source_url,
            )

            cmd = self._build_ffmpeg_cmd()
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._state = "running"
                return True
            except Exception:
                logger.exception("Reconnect failed")
                self._state = "error"
                return False

    # -- Internal helpers -----------------------------------------------------

    def _build_ffmpeg_cmd(self) -> list:
        """Build the FFmpeg command list for the validated RTSP source."""
        cmd = [
            "ffmpeg",
            "-protocol_whitelist", "rtsp,rtsps,tcp,tls",
            "-rtsp_transport", "tcp",
        ]

        cmd += [
            "-i", self.source_url,
            "-vn",
            "-f", "s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1",
            "-loglevel", "error",
            "pipe:1",
        ]
        return cmd

    def _handle_disconnect(self) -> None:
        """Mark stream as reconnecting (caller is responsible for waiting)."""
        self._state = "reconnecting"

    def _terminate_process(self) -> None:
        """Kill the FFmpeg process if alive.  Must be called under _lock."""
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                self._process.kill()
        self._process = None
