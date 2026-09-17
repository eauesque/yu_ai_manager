"""Main processing loop for real-time stream transcription.

Runs in a background thread spawned by stream_state.start_stream().
All core.* imports are local (inside function body) to avoid circular
imports and match the pattern used in s2t_batch_resolvers.py.
"""

import contextlib
import logging
import os
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-speech-to-text"
_UNLOAD_AFTER_STREAM = os.environ.get("YU_S2T_UNLOAD_AFTER_STREAM", "1").strip().lower() not in {
    "0", "false", "no", "off",
}


def run_stream_worker(
    source_url: str,
    language: str,
    model_size: str = "",
    stop_fn: Callable[[], bool] = lambda: False,
    finish_fn: Callable[..., None] = lambda *a, **kw: None,
) -> None:
    """Capture audio from a URL/stream and transcribe in real time.

    Args:
        source_url: FFmpeg-compatible source URL or file path.
        language: Language code for transcription (e.g. "ja", "en").
        stop_fn: Returns True when the worker should stop.
        finish_fn: Called on completion with (reason, error=).
    """
    # Local imports — core.* must not be at module top level
    from core.event_bus import emit
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

    from .backend_registry import get_backend
    from .stream_capture import StreamCapture
    from .stream_chunker import StreamChunker
    from .stream_state import add_segments

    backend_pref = get_extension_config_value(_EXT_NAME, "backend", "auto")
    if not model_size:
        model_size = get_extension_config_value(_EXT_NAME, "model_size", "base")

    # Chunker settings from extension config
    chunk_min = float(get_extension_config_value(_EXT_NAME, "stream_chunk_min_sec", 3))
    chunk_max = float(get_extension_config_value(_EXT_NAME, "stream_chunk_max_sec", 10))
    silence_thresh = float(get_extension_config_value(_EXT_NAME, "stream_silence_threshold", 500))
    silence_ms = int(get_extension_config_value(_EXT_NAME, "stream_silence_ms", 500))

    capture: StreamCapture | None = None
    reason = "complete"
    error_msg: str | None = None

    try:
        # Initialize backend
        try:
            backend = get_backend(backend_pref, model_size)
        except Exception as exc:
            exc_str = str(exc)
            # Some HailoRT builds obscure host-memory allocation errors behind
            # a formatting exception. Normalize legacy and current forms.
            _memory_hint = (
                "OUT_OF_HOST_MEMORY" in exc_str
                or "CMA memory exhausted" in exc_str
                or "unmatched '}' in format string" in exc_str
                or "insufficient CMA" in exc_str
                or "host-memory allocation error" in exc_str
            )
            if _memory_hint:
                error_msg = (
                    f"Backend init failed because HailoRT reported a host-memory "
                    f"allocation error: {exc}. Stop unused Hailo workloads and retry. "
                    f"Low CmaFree alone does not require a reboot."
                )
            else:
                error_msg = f"Backend init failed: {exc}"
            logger.error(error_msg, exc_info=True)
            emit("s2t.stream_error", {"error": error_msg}, source="s2t")
            finish_fn("error", error=error_msg)
            return

        emit("s2t.stream_start", {
            "source_url": source_url,
            "language": language,
            "backend": backend.name,
        }, source="s2t")

        # Create capture and chunker
        sample_rate = 16000
        capture = StreamCapture(source_url, sample_rate=sample_rate)
        chunker = StreamChunker(
            sample_rate=sample_rate,
            min_chunk_sec=chunk_min,
            max_chunk_sec=chunk_max,
            silence_threshold=silence_thresh,
            min_silence_ms=silence_ms,
        )

        capture.start()
        if capture.state == "error":
            error_msg = "FFmpeg failed to start"
            logger.error(error_msg)
            emit("s2t.stream_error", {"error": error_msg}, source="s2t")
            finish_fn("error", error=error_msg)
            return

        chunk_index = 0
        total_input_samples = 0
        buffer_start_sample = 0

        # Main loop
        while not stop_fn():
            audio = capture.read_chunk(1.0)

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

            # Feed audio to chunker
            chunker.feed(audio)
            if total_input_samples == 0:
                logger.debug("[S2T-DEBUG] First audio: %d samples", len(audio))
                logger.info("Stream: first audio received (%d samples)", len(audio))

            # Log chunker state periodically
            pending = chunker.pending_duration()
            if int(pending) % 10 == 0 and int(pending) > 0 and int(pending) != getattr(run_stream_worker, '_last_log_sec', -1):
                run_stream_worker._last_log_sec = int(pending)
                logger.info("Stream: %.1fs audio buffered, %d chunks processed", pending, chunk_index)

            total_input_samples += len(audio)

            # Try to extract a complete chunk
            chunk = chunker.try_extract()
            if total_input_samples % (sample_rate * 5) < sample_rate:
                logger.debug(
                    "[S2T-DEBUG] loop: pending=%.1fs, total_fed=%.1fs, chunk=%s",
                    chunker.pending_duration(),
                    total_input_samples / sample_rate,
                    "YES" if chunk is not None else "None",
                )
            if chunk is not None:
                logger.debug("[S2T-DEBUG] Chunk extracted: %d samples (%.1fs)", len(chunk), len(chunk) / sample_rate)
                _process_chunk(
                    chunk, backend, language, sample_rate,
                    buffer_start_sample, chunk_index,
                    add_segments, emit,
                )
                overlap_samples = int(getattr(chunker, "_overlap_samples", 0))
                buffer_start_sample += max(0, len(chunk) - overlap_samples)
                chunk_index += 1

        # Flush remaining audio on stop
        if stop_fn():
            reason = "stopped"

        remaining = chunker.flush()
        if remaining is not None and len(remaining) > 0:
            _process_chunk(
                remaining, backend, language, sample_rate,
                buffer_start_sample, chunk_index,
                add_segments, emit,
            )
            chunk_index += 1

    except Exception as exc:
        logger.exception("Stream worker unexpected error")
        error_msg = str(exc)
        reason = "error"
    finally:
        if capture is not None:
            with contextlib.suppress(Exception):
                capture.stop()
        if _UNLOAD_AFTER_STREAM:
            with contextlib.suppress(Exception):
                from .backend_registry import close_backend
                close_backend()

        finish_fn(reason, error=error_msg)

        from core.event_bus import emit as _emit
        _emit("s2t.stream_complete", {
            "reason": reason,
            "error": error_msg,
        }, source="s2t")


def _process_chunk(
    chunk,
    backend,
    language: str,
    sample_rate: int,
    chunk_start_sample: int,
    chunk_index: int,
    add_segments_fn: Callable,
    emit_fn: Callable,
) -> None:
    """Transcribe a single audio chunk and emit results."""
    import numpy as np

    # Convert int16 to float32 normalized
    chunk_f32 = chunk.astype(np.float32) / 32768.0

    logger.debug("[S2T-DEBUG] _process_chunk called: chunk_index=%d, chunk_len=%d", chunk_index, len(chunk))
    try:
        segments = backend.transcribe(chunk_f32, language=language)
        text_preview = " ".join(s.get("text", "") for s in segments)[:100] if segments else "[]"
        logger.debug("[S2T-DEBUG] Chunk %d: %d segments, text=%r", chunk_index, len(segments), text_preview)
    except Exception:
        logger.debug("[S2T-DEBUG] Chunk %d: transcription FAILED", chunk_index)
        logger.exception("Transcription failed for chunk %d", chunk_index)
        return

    if not segments:
        logger.debug("[S2T-DEBUG] Chunk %d: no segments returned", chunk_index)
        return

    # Adjust segment timestamps by the absolute start time of this chunk.
    offset = chunk_start_sample / sample_rate
    for seg in segments:
        seg["start"] = seg.get("start", 0.0) + offset
        seg["end"] = seg.get("end", 0.0) + offset

    add_segments_fn(segments)

    text = " ".join(seg.get("text", "") for seg in segments).strip()
    emit_fn("s2t.stream_chunk", {
        "chunk_index": chunk_index,
        "text": text,
        "segments": segments,
    }, source="s2t")
