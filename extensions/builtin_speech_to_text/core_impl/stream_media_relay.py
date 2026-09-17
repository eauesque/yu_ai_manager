"""Fragmented MP4 relay for validated RTSP/RTSPS sources."""

import contextlib
import logging
import subprocess
import threading

logger = logging.getLogger(__name__)


class MediaRelay:
    """FFmpeg fMP4 relay — copy codecs, single process for video+audio."""

    def __init__(self, source_url: str) -> None:
        self.source_url = source_url
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Spawn FFmpeg subprocess for fMP4 output."""
        with self._lock:
            if self._process is not None:
                return
            cmd = self._build_cmd()
            logger.info("MediaRelay starting: %s", " ".join(cmd))
            try:
                self._process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                # Read stderr in background thread to prevent pipe blockage
                self._stderr_thread = threading.Thread(
                    target=self._drain_stderr,
                    daemon=True,
                    name="media-relay-stderr",
                )
                self._stderr_thread.start()
            except FileNotFoundError:
                logger.error("ffmpeg not found on PATH")
            except Exception:
                logger.exception("Failed to start MediaRelay FFmpeg")

    def read(self, size: int = 8192) -> bytes:
        """Read fMP4 data from FFmpeg stdout."""
        with self._lock:
            proc = self._process
        if proc is None or proc.stdout is None:
            return b""
        try:
            data = proc.stdout.read(size)
            if not data:
                # FFmpeg exited — log return code
                rc = proc.poll()
                logger.warning("MediaRelay FFmpeg exited (rc=%s)", rc)
            return data if data else b""
        except Exception:
            logger.exception("Error reading from MediaRelay pipe")
            return b""

    def stop(self) -> None:
        """Terminate the FFmpeg process."""
        with self._lock:
            if self._process is None:
                return
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                with contextlib.suppress(Exception):
                    self._process.kill()
            self._process = None

    def _drain_stderr(self) -> None:
        """Read stderr in background to prevent pipe blockage, log errors."""
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    logger.warning("MediaRelay FFmpeg: %s", text)
        except Exception:
            logger.debug("stderr relay ended early", exc_info=True)

    @staticmethod
    def _is_audio_only(url: str) -> bool:
        """Heuristic: URL likely contains only audio streams."""
        u = url.lower()
        segments = u.split("/")
        # Path segment literally named "audio" → audio-only
        if "audio" in segments:
            return True
        # Filename contains "audio" but not "video"
        filename = segments[-1].split("?")[0]
        return bool("audio" in filename and "video" not in filename)

    def _build_cmd(self) -> list:
        """Build FFmpeg command for the validated RTSP source."""
        cmd = [
            "ffmpeg",
            "-protocol_whitelist", "rtsp,rtsps,tcp,tls",
            "-rtsp_transport", "tcp",
        ]

        audio_only = self._is_audio_only(self.source_url)

        cmd += [
            # Reduce input buffering for lower latency
            "-fflags", "+nobuffer+discardcorrupt+genpts",
            "-flags", "low_delay",
            "-err_detect", "ignore_err",
            "-i", self.source_url,
        ]

        if audio_only:
            # Audio-only source: skip all video options
            cmd += ["-vn"]
        else:
            # Video+audio source: lightweight H.264 re-encode
            # (avoids codec-copy timestamp issues with live streams)
            cmd += [
                "-map", "0:v?",   # include video if present (optional)
                "-map", "0:a",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-crf", "30",
                "-vf", "scale=640:-2",
                "-r", "15",
                "-g", "30",       # keyframe every 2s at 15fps
            ]

        cmd += [
            # Audio: re-encode to AAC for browser compatibility
            "-c:a", "aac", "-b:a", "128k",
            # Output: fragmented MP4 for live streaming
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-frag_duration", "1000000",
            "-flush_packets", "1",
            "-max_delay", "0",
            "-loglevel", "warning",
            "pipe:1",
        ]
        return cmd
