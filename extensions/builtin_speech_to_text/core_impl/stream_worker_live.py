"""Live streaming transcription worker (Phase B).

Uses faster-whisper's built-in Silero VAD to periodically transcribe
the accumulated audio buffer, emitting both final (confirmed) and
interim (tentative) results via SSE.

Architecture:
    FFmpeg -> PCM 16kHz mono -> ring buffer (numpy int16)
        -> every N seconds, run faster-whisper.transcribe(vad_filter=True)
        -> compare with previous results:
            - confirmed segments -> SSE "s2t.stream_final" + "s2t.stream_chunk"
            - last tentative segment -> SSE "s2t.stream_interim"
        -> trim confirmed audio from buffer

All core.* imports are local (inside function body) to avoid circular
imports — same pattern as stream_worker.py.
"""

import contextlib
import logging
import time
from collections.abc import Callable

import numpy as np

from .stream_worker_live_transcribe import flush_buffer, transcribe_buffer

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-speech-to-text"
_DEFAULT_INTERVAL = 3.0   # seconds between transcription runs
_MIN_AUDIO_SEC = 1.0      # minimum audio length to attempt transcription
_SAMPLE_RATE = 16000
_READ_CHUNK_SEC = 0.5     # seconds per capture read


def run_stream_worker_live(
    source_url: str,
    language: str,
    model_size: str = "",
    stop_fn: Callable[[], bool] = lambda: False,
    finish_fn: Callable[..., None] = lambda *a, **kw: None,
) -> None:
    """Capture audio from a URL/stream and transcribe in live mode.

    Emits interim results during speech and final results when segments
    are confirmed.  Uses faster-whisper backend directly with VAD.

    Args:
        source_url: FFmpeg-compatible source URL or file path.
        language: Language code for transcription (e.g. "ja", "en").
        model_size: Whisper model size (e.g. "base", "small").
        stop_fn: Returns True when the worker should stop.
        finish_fn: Called on completion with (reason, error=).
    """
    # Local imports — core.* must not be at module top level
    from core.event_bus import emit
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

    from .backend_faster_whisper import FasterWhisperBackend
    from .stream_capture import StreamCapture
    from .stream_state import add_segments

    if not model_size:
        model_size = get_extension_config_value(_EXT_NAME, "model_size", "base")

    interval = float(
        get_extension_config_value(_EXT_NAME, "live_interval_sec", _DEFAULT_INTERVAL)
    )

    capture: StreamCapture | None = None
    backend: FasterWhisperBackend | None = None
    reason = "complete"
    error_msg: str | None = None

    try:
        # Initialize faster-whisper backend directly (live mode requires it)
        try:
            backend = FasterWhisperBackend()
            backend.load_model(model_size)
        except Exception as exc:
            error_msg = f"Backend init failed: {exc}"
            logger.error(error_msg)
            emit("s2t.stream_error", {"error": error_msg}, source="s2t")
            finish_fn("error", error=error_msg)
            return

        emit("s2t.stream_start", {
            "source_url": source_url,
            "language": language,
            "backend": backend.name,
            "mode": "live",
        }, source="s2t")

        # Create capture
        capture = StreamCapture(source_url, sample_rate=_SAMPLE_RATE)
        capture.start()

        if capture.state == "error":
            error_msg = "FFmpeg failed to start"
            logger.error(error_msg)
            emit("s2t.stream_error", {"error": error_msg}, source="s2t")
            finish_fn("error", error=error_msg)
            return

        # Run the live loop
        reason, error_msg = _live_loop(
            capture=capture,
            backend=backend,
            language=language,
            interval=interval,
            stop_fn=stop_fn,
            add_segments_fn=add_segments,
            emit_fn=emit,
        )

    except Exception as exc:
        logger.exception("Live stream worker unexpected error")
        error_msg = str(exc)
        reason = "error"
    finally:
        if capture is not None:
            with contextlib.suppress(Exception):
                capture.stop()
        if backend is not None:
            with contextlib.suppress(Exception):
                backend.close()

        finish_fn(reason, error=error_msg)

        from core.event_bus import emit as _emit
        _emit("s2t.stream_complete", {
            "reason": reason,
            "error": error_msg,
        }, source="s2t")


def _live_loop(
    capture,
    backend,
    language: str,
    interval: float,
    stop_fn: Callable[[], bool],
    add_segments_fn: Callable,
    emit_fn: Callable,
) -> tuple:
    """Main live transcription loop.

    Returns:
        (reason, error_msg) tuple.
    """
    # Audio buffer — int16 samples accumulated from capture
    buf = np.array([], dtype=np.int16)
    chunk_index = 0
    total_offset_sec = 0.0  # cumulative time of confirmed audio
    last_transcribe_time = time.monotonic()
    reason = "complete"
    error_msg: str | None = None

    while not stop_fn():
        audio = capture.read_chunk(_READ_CHUNK_SEC)

        if audio is None:
            state = capture.state
            if state == "error":
                error_msg = "Stream capture error (FFmpeg)"
                reason = "error"
                break

            if state == "reconnecting":
                # Wait in small increments, checking stop_fn
                for _ in range(10):
                    if stop_fn():
                        break
                    time.sleep(0.5)
                if stop_fn():
                    break
                if not capture.try_reconnect():
                    error_msg = "Reconnect failed after max attempts"
                    reason = "error"
                    break
                continue

            # Stopped or other — skip
            continue

        # Accumulate audio
        buf = np.concatenate([buf, audio])

        # Check if it's time to transcribe
        now = time.monotonic()
        if now - last_transcribe_time < interval:
            continue
        last_transcribe_time = now

        buf_duration = len(buf) / _SAMPLE_RATE
        if buf_duration < _MIN_AUDIO_SEC:
            continue

        # Transcribe the accumulated buffer
        chunk_index, buf, total_offset_sec = transcribe_buffer(
            buf=buf,
            backend=backend,
            language=language,
            total_offset_sec=total_offset_sec,
            chunk_index=chunk_index,
            add_segments_fn=add_segments_fn,
            emit_fn=emit_fn,
        )

    # Determine stop reason
    if stop_fn():
        reason = "stopped"

    # Flush remaining buffer
    if len(buf) > 0:
        buf_duration = len(buf) / _SAMPLE_RATE
        if buf_duration >= _MIN_AUDIO_SEC:
            flush_buffer(
                buf=buf,
                backend=backend,
                language=language,
                total_offset_sec=total_offset_sec,
                chunk_index=chunk_index,
                add_segments_fn=add_segments_fn,
                emit_fn=emit_fn,
            )

    return reason, error_msg
