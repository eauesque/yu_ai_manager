"""Thread-safe state management for real-time stream transcription."""

import ipaddress
import logging
import os
import socket
import threading
import time
from urllib.parse import urlparse

from .stream_audio_relay import AudioRelay
from .stream_media_relay import MediaRelay
from .stream_video_relay import VideoRelay

logger = logging.getLogger(__name__)


def _pin_stream_source_url(source_url: str) -> tuple[str | None, str | None]:
    """Resolve once and replace a stream hostname with its validated public IP."""
    parsed = urlparse(source_url)
    if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname:
        return None, "source_url must use rtsp/rtsps protocol"
    if parsed.username or parsed.password:
        return None, "source_url must not contain credentials"
    try:
        infos = socket.getaddrinfo(parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return None, "source_url host could not be resolved"
    if not infos or any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        return None, "Internal addresses are not allowed"
    peer_ip = infos[0][4][0]
    host = f"[{peer_ip}]" if ":" in peer_ip else peer_ip
    netloc = f"{host}:{parsed.port}" if parsed.port else host
    return parsed._replace(netloc=netloc).geturl(), None


def validate_stream_source_url(source_url: str) -> str | None:
    """Reject non-public stream sources before any FFmpeg process starts."""
    _, error = _pin_stream_source_url(source_url)
    return error


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using %s", name, value, default)
        return default


_TRANSCRIPT_MAX_SEGMENTS = _env_int("YU_S2T_TRANSCRIPT_MAX_SEGMENTS", 2000)

_state_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_stop_requested = False
_audio_relay: AudioRelay | None = None
_video_relay: VideoRelay | None = None
_media_relay: MediaRelay | None = None
_state = {
    "running": False,
    "source_url": "",
    "language": "ja",
    "mode": "chunk",
    "video_mode": "mjpeg",
    "started_at": 0.0,
    "chunks_processed": 0,
    "total_text_length": 0,
    "error": None,
}
_transcript: list[dict] = []
_transcript_dropped = 0


def get_status() -> dict:
    """Return current stream state with elapsed time and segment count."""
    with _state_lock:
        status = dict(_state)
    elapsed = round(time.time() - status["started_at"], 1) if status["running"] and status["started_at"] else 0.0
    status["elapsed"] = elapsed
    status["elapsed_seconds"] = elapsed  # alias for UI compatibility
    with _state_lock:
        status["transcript_segments"] = len(_transcript)
        status["transcript_dropped"] = _transcript_dropped
    return status


def get_transcript() -> list[dict]:
    """Return accumulated transcript segments."""
    with _state_lock:
        return list(_transcript)


def get_transcript_dropped_count() -> int:
    """Return how many old transcript segments were evicted from memory."""
    with _state_lock:
        return _transcript_dropped


def add_segments(segments: list[dict]) -> None:
    """Append new transcript segments and update counters."""
    global _transcript_dropped
    if not segments:
        return
    text_len = sum(len(seg.get("text", "")) for seg in segments)
    with _state_lock:
        _transcript.extend(segments)
        if _TRANSCRIPT_MAX_SEGMENTS > 0 and len(_transcript) > _TRANSCRIPT_MAX_SEGMENTS:
            overflow = len(_transcript) - _TRANSCRIPT_MAX_SEGMENTS
            del _transcript[:overflow]
            _transcript_dropped += overflow
        _state["chunks_processed"] += 1
        _state["total_text_length"] += text_len


def start_stream(source_url: str, language: str = "ja", model_size: str = "",
                  mode: str = "chunk") -> dict:
    """Start stream transcription in a background thread.

    Returns status dict.  Raises nothing — errors are reported in the dict.
    """
    global _worker_thread, _stop_requested, _transcript_dropped

    pinned_source, url_error = _pin_stream_source_url(source_url)
    if url_error:
        return {"status": "error", "message": url_error}
    source_url = pinned_source or source_url

    with _state_lock:
        if _state["running"]:
            return {"status": "already_running", **_state}

        _stop_requested = False
        video_mode = "mjpeg"
        _state.update({
            "running": True,
            "source_url": source_url,
            "language": language,
            "mode": mode,
            "video_mode": video_mode,
            "started_at": time.time(),
            "chunks_processed": 0,
            "total_text_length": 0,
            "error": None,
        })
        _transcript.clear()
        _transcript_dropped = 0

    # Live mode requires faster-whisper backend
    if mode == "live":
        from .backend_faster_whisper import FasterWhisperBackend
        if not FasterWhisperBackend.is_available():
            with _state_lock:
                _state["running"] = False
            return {"status": "error",
                    "message": "Live mode requires faster-whisper (pip install faster-whisper)"}

    global _audio_relay, _video_relay, _media_relay

    _media_relay = None
    _audio_relay = AudioRelay(source_url)
    _audio_relay.start()
    _video_relay = VideoRelay(source_url)
    _video_relay.start()

    # Select worker function based on mode
    if mode == "live":
        from .stream_worker_live import run_stream_worker_live
        worker_fn = run_stream_worker_live
    else:
        from .stream_worker import run_stream_worker
        worker_fn = run_stream_worker

    _worker_thread = threading.Thread(
        target=worker_fn,
        kwargs={
            "source_url": source_url,
            "language": language,
            "model_size": model_size,
            "stop_fn": lambda: _stop_requested,
            "finish_fn": _finish_stream,
        },
        name="s2t-stream-worker",
        daemon=True,
    )
    _worker_thread.start()
    logger.info("Stream transcription started: %s (lang=%s, video=%s)",
                source_url, language, video_mode)
    return {
        "status": "started",
        "source_url": source_url,
        "language": language,
        "video_mode": video_mode,
    }


def stop_stream() -> dict:
    """Request the stream worker to stop and wait for it to finish."""
    global _stop_requested, _audio_relay, _video_relay, _media_relay
    with _state_lock:
        if not _state["running"]:
            return {"status": "not_running"}
        _stop_requested = True
        thread = _worker_thread

    # Stop all relays
    if _audio_relay is not None:
        _audio_relay.stop()
        _audio_relay = None
    if _video_relay is not None:
        _video_relay.stop()
        _video_relay = None
    if _media_relay is not None:
        _media_relay.stop()
        _media_relay = None

    logger.info("Stream transcription stop requested")

    # Wait for the worker thread to finish (up to 10 seconds)
    if thread is not None and thread.is_alive():
        thread.join(timeout=10)
        if thread.is_alive():
            logger.warning("Stream worker did not stop within 10s, forcing cleanup")
            with _state_lock:
                _state["running"] = False
                _state["error"] = "Force stopped (worker timeout)"

    return {"status": "stopped"}


def get_audio_relay() -> AudioRelay | None:
    """Return the active audio relay, or None if not running."""
    return _audio_relay


def get_video_relay() -> VideoRelay | None:
    """Return the active video relay, or None if not running."""
    return _video_relay


def get_media_relay() -> MediaRelay | None:
    """Return the active media relay, or None if not running."""
    return _media_relay


def restart_media_relay() -> MediaRelay | None:
    """Restart the media relay if the stream is still active but FFmpeg died."""
    global _media_relay
    with _state_lock:
        if not _state["running"] or not _state["source_url"]:
            return None
        source_url = _state["source_url"]

    # Stop the dead relay
    if _media_relay is not None:
        _media_relay.stop()

    # Start a fresh one
    _media_relay = MediaRelay(source_url)
    _media_relay.start()
    logger.info("MediaRelay restarted for %s", source_url)
    return _media_relay


def _finish_stream(reason: str, error: str | None = None) -> None:
    """Clean up after stream worker completes or errors out."""
    global _worker_thread, _audio_relay, _video_relay, _media_relay
    if _audio_relay is not None:
        _audio_relay.stop()
        _audio_relay = None
    if _video_relay is not None:
        _video_relay.stop()
        _video_relay = None
    if _media_relay is not None:
        _media_relay.stop()
        _media_relay = None
    with _state_lock:
        _state["running"] = False
        _state["error"] = error
        _worker_thread = None
    logger.info("Stream transcription finished: %s (error=%s)", reason, error)
