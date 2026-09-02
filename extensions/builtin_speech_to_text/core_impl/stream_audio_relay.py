"""Audio relay for browser playback of the stream source.

Runs a separate FFmpeg process that reads the same source URL
and outputs MP3 for browser <audio> playback.
"""

import contextlib
import logging
import subprocess
import threading

logger = logging.getLogger(__name__)


class AudioRelay:
    """Spawn FFmpeg to transcode a stream URL to MP3 for browser playback."""

    def __init__(self, source_url: str) -> None:
        self.source_url = source_url
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Spawn the FFmpeg subprocess for MP3 output."""
        with self._lock:
            if self._process is not None:
                return
            cmd = self._build_ffmpeg_cmd()
            logger.info("AudioRelay starting: %s", " ".join(cmd))
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                logger.error("ffmpeg not found on PATH")
            except Exception:
                logger.exception("Failed to start AudioRelay FFmpeg")

    def read(self, size: int = 4096) -> bytes:
        """Read MP3 data from FFmpeg stdout.

        Returns empty bytes when no data is available or stream ended.
        """
        with self._lock:
            if self._process is None or self._process.stdout is None:
                return b""
            try:
                data = self._process.stdout.read(size)
                return data if data else b""
            except Exception:
                logger.exception("Error reading from AudioRelay pipe")
                return b""

    def stop(self) -> None:
        """Terminate the FFmpeg process."""
        with self._lock:
            self._terminate_process()

    def _build_ffmpeg_cmd(self) -> list:
        """Build FFmpeg command for the validated RTSP source."""
        cmd = [
            "ffmpeg",
            "-protocol_whitelist", "rtsp,rtsps,tcp,tls",
            "-rtsp_transport", "tcp",
        ]

        cmd += [
            "-i", self.source_url,
            "-vn",
            "-f", "mp3",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            "-loglevel", "error",
            "pipe:1",
        ]
        return cmd

    def _terminate_process(self) -> None:
        """Kill the FFmpeg process if alive. Must be called under _lock."""
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except Exception:
            with contextlib.suppress(Exception):
                self._process.kill()
        self._process = None
