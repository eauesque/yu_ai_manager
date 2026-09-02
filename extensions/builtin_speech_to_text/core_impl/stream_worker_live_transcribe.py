"""Transcription helpers for the live speech-to-text worker."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

_KEEP_TAIL_SEC = 2.0
_SAMPLE_RATE = 16000


def transcribe_buffer(
    buf: np.ndarray,
    backend,
    language: str,
    total_offset_sec: float,
    chunk_index: int,
    add_segments_fn: Callable,
    emit_fn: Callable,
) -> tuple:
    """Transcribe the current buffer, emit finals/interim, and trim confirmed audio."""
    audio_f32 = buf.astype(np.float32) / 32768.0

    try:
        segments_iter, _info = backend.transcribe_raw(
            audio_f32,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        raw_segments = [
            {"text": seg.text.strip(), "start": round(seg.start, 3), "end": round(seg.end, 3)}
            for seg in segments_iter
        ]
    except Exception:
        logger.exception("Live transcription failed")
        return chunk_index, buf, total_offset_sec

    if not raw_segments:
        keep_samples = int(_KEEP_TAIL_SEC * _SAMPLE_RATE)
        if len(buf) > keep_samples:
            trimmed = len(buf) - keep_samples
            total_offset_sec += trimmed / _SAMPLE_RATE
            buf = buf[-keep_samples:]
        return chunk_index, buf, total_offset_sec

    if len(raw_segments) > 1:
        final_segments = raw_segments[:-1]
        interim_segment = raw_segments[-1]
    else:
        final_segments = []
        interim_segment = raw_segments[0]

    if final_segments:
        for segment in final_segments:
            segment["start"] = round(segment["start"] + total_offset_sec, 3)
            segment["end"] = round(segment["end"] + total_offset_sec, 3)

        add_segments_fn(final_segments)
        text = " ".join(segment["text"] for segment in final_segments).strip()
        payload = {"chunk_index": chunk_index, "text": text, "segments": final_segments}
        emit_fn("s2t.stream_final", payload, source="s2t")
        emit_fn("s2t.stream_chunk", payload, source="s2t")
        chunk_index += 1

        last_final_end = raw_segments[-2]["end"]
        trim_samples = int(last_final_end * _SAMPLE_RATE)
        if trim_samples > 0 and trim_samples < len(buf):
            total_offset_sec += trim_samples / _SAMPLE_RATE
            buf = buf[trim_samples:]
        elif trim_samples >= len(buf):
            total_offset_sec += len(buf) / _SAMPLE_RATE
            buf = np.array([], dtype=np.int16)

    if interim_segment and interim_segment["text"]:
        emit_fn(
            "s2t.stream_interim",
            {"text": interim_segment["text"], "offset": round(interim_segment["start"] + total_offset_sec, 3)},
            source="s2t",
        )

    return chunk_index, buf, total_offset_sec


def flush_buffer(
    buf: np.ndarray,
    backend,
    language: str,
    total_offset_sec: float,
    chunk_index: int,
    add_segments_fn: Callable,
    emit_fn: Callable,
) -> None:
    """Transcribe remaining buffer as final segments on stop."""
    audio_f32 = buf.astype(np.float32) / 32768.0

    try:
        segments_iter, _info = backend.transcribe_raw(
            audio_f32,
            language=language,
            beam_size=5,
            vad_filter=True,
        )
        segments = [
            {
                "text": seg.text.strip(),
                "start": round(seg.start + total_offset_sec, 3),
                "end": round(seg.end + total_offset_sec, 3),
            }
            for seg in segments_iter
        ]
    except Exception:
        logger.exception("Flush transcription failed")
        return

    if not segments:
        return

    add_segments_fn(segments)
    text = " ".join(segment["text"] for segment in segments).strip()
    payload = {"chunk_index": chunk_index, "text": text, "segments": segments}
    emit_fn("s2t.stream_final", payload, source="s2t")
    emit_fn("s2t.stream_chunk", payload, source="s2t")
