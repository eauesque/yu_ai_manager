"""Video relay for browser preview of the stream source.

Runs a separate FFmpeg process that reads the same source URL
and outputs MJPEG frames for browser <img> preview.
"""

import contextlib
import logging
import subprocess
import threading

logger = logging.getLogger(__name__)


class VideoRelay:
    """Spawn FFmpeg to transcode a stream URL to MJPEG for browser preview."""

    def __init__(
        self, source_url: str, fps: int = 5, width: int = 640
    ) -> None:
        self.source_url = source_url
        self.fps = fps
        self.width = width
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._remainder = b""

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Spawn the FFmpeg subprocess for MJPEG output."""
        with self._lock:
            if self._process is not None:
                return
            cmd = self._build_ffmpeg_cmd()
            logger.info("VideoRelay starting: %s", " ".join(cmd))
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                logger.error("ffmpeg not found on PATH")
            except Exception:
                logger.exception("Failed to start VideoRelay FFmpeg")

    def read_frame(self) -> bytes | None:
        """Read one complete JPEG frame from FFmpeg stdout.

        Each JPEG frame starts with SOI marker (0xFFD8).
        Returns None when the stream ends or process is not running.
        """
        with self._lock:
            if self._process is None or self._process.stdout is None:
                return None

        # Read chunks and split on SOI boundaries
        while True:
            with self._lock:
                if self._process is None or self._process.stdout is None:
                    break
                stdout = self._process.stdout
            try:
                chunk = stdout.read(8192)
            except Exception:
                logger.exception("Error reading from VideoRelay pipe")
                return None
            if not chunk:
                # Stream ended — return any buffered remainder
                if self._remainder:
                    frame = self._remainder
                    self._remainder = b""
                    return frame
                return None
            self._remainder += chunk
            # Find second SOI marker (start of next frame)
            idx = self._remainder.find(b"\xff\xd8", 2)
            if idx > 0:
                frame = self._remainder[:idx]
                self._remainder = self._remainder[idx:]
                return frame
            # Safety limit: avoid unbounded buffering (~500KB)
            if len(self._remainder) > 500000:
                frame = self._remainder
                self._remainder = b""
                return frame

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
            "-an",
            "-f", "image2pipe",
            "-c:v", "mjpeg",
            "-q:v", "5",
            "-r", str(self.fps),
            "-vf", f"scale={self.width}:-1",
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
        self._remainder = b""
