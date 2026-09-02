"""Local Whisper transcription using faster-whisper (ONNX/CTranslate2)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Check if faster-whisper is installed."""
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import faster_whisper  # noqa: F401
            _AVAILABLE = True
        except ImportError:
            _AVAILABLE = False
    return _AVAILABLE


def transcribe(
    audio_path: Path,
    model_size: str = "base",
    language: str = "",
    compute_type: str = "int8",
) -> dict:
    """Transcribe audio file using faster-whisper.

    Args:
        audio_path: Path to WAV/audio file.
        model_size: "tiny", "base", "small", "medium", "large-v3".
        language: ISO 639-1 code (e.g. "ja", "en"). Empty for auto-detect.
        compute_type: "int8", "float16", "float32".

    Returns:
        {"text": str, "segments": list, "language": str, "duration": float}
    """
    if not is_available():
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Install: uv pip install faster-whisper"
        )

    from faster_whisper import WhisperModel

    logger.info(
        "Whisper transcribe: model=%s, lang=%s, file=%s",
        model_size, language or "auto", audio_path.name,
    )

    model = WhisperModel(model_size, compute_type=compute_type)

    kwargs = {}
    if language:
        kwargs["language"] = language

    segments_iter, info = model.transcribe(str(audio_path), **kwargs)

    segments: list[dict] = []
    full_text_parts: list[str] = []

    for seg in segments_iter:
        segments.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text.strip(),
        })
        full_text_parts.append(seg.text.strip())

    full_text = " ".join(full_text_parts)

    return {
        "text": full_text,
        "segments": segments,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
    }
