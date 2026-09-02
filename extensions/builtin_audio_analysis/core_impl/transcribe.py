"""Audio transcription orchestrator.

Coordinates audio extraction and transcription via local Whisper or API.
Stores results in the existing analysis table.
"""

import json
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_ANALYSIS_PATH_ADDED = False


def _ensure_analysis_path():
    """Add the builtin_analysis directory to sys.path for cross-extension imports."""
    global _ANALYSIS_PATH_ADDED
    if _ANALYSIS_PATH_ADDED:
        return
    ext_path = str(Path(__file__).resolve().parent.parent.parent / "builtin_analysis")
    if ext_path not in sys.path:
        sys.path.insert(0, ext_path)
    _ANALYSIS_PATH_ADDED = True


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or M:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_description(result: dict) -> str:
    """Build human-readable description from transcription result."""
    text = result.get("text", "").strip()
    lang = result.get("language", "")
    duration = result.get("duration", 0)

    parts = []
    if duration > 0:
        parts.append(f"[{_format_timestamp(duration)}]")
    if lang:
        parts.append(f"[{lang}]")
    if parts:
        header = " ".join(parts)
        return f"{header}\n\n{text}"
    return text


def _build_segments_text(segments: list) -> str:
    """Build timestamped transcript from segments."""
    lines = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        lines.append(f"[{ts}] {seg['text']}")
    return "\n".join(lines)


def _to_analysis_result(result: dict):
    """Convert transcription dict to AnalysisResult for DB storage."""
    _ensure_analysis_path()
    from core_impl.types import AnalysisResult

    ar = AnalysisResult()
    ar.description = _build_description(result)
    ar.quality_notes = f"Duration: {_format_timestamp(result.get('duration', 0))}"
    if result.get("language"):
        ar.quality_notes += f" | Language: {result['language']}"
    ar.raw_response = json.dumps(result, ensure_ascii=False)

    # Store timestamped transcript in prompt_suggestion for easy reading
    segments = result.get("segments", [])
    if segments:
        ar.prompt_suggestion = _build_segments_text(segments)

    return ar


def transcribe_file(
    file_path: str,
    engine: str = "whisper_local",
    model: str = "base",
    language: str = "",
    api_key: str = "",
    base_url: str = "",
) -> tuple[dict, str]:
    """Transcribe an audio/video file.

    Returns:
        (transcription_dict, engine_label)
    """
    from .audio_extract import extract_audio, is_audio_file

    src = Path(file_path)
    if not src.exists():
        raise RuntimeError(f"File not found: {file_path}")

    wav_path = None
    tmp_dir = None
    try:
        if is_audio_file(file_path) and src.suffix.lower() == ".wav":
            wav_path = src
        else:
            wav_path = extract_audio(file_path)
            if wav_path is None:
                raise RuntimeError(
                    "Failed to extract audio (no audio track or ffmpeg error)"
                )
            tmp_dir = wav_path.parent

        if engine == "whisper_api":
            from .whisper_api import transcribe as api_transcribe
            result = api_transcribe(
                wav_path,
                api_key=api_key,
                model=model or "whisper-1",
                language=language,
                base_url=base_url,
            )
            engine_label = f"Whisper API ({model or 'whisper-1'})"
        else:
            from .whisper_local import transcribe as local_transcribe
            result = local_transcribe(
                wav_path,
                model_size=model or "base",
                language=language,
            )
            engine_label = f"Whisper ({model or 'base'})"

        return result, engine_label

    finally:
        if tmp_dir and tmp_dir != src.parent:
            shutil.rmtree(str(tmp_dir), ignore_errors=True)


def transcribe_and_save(
    file_id: int,
    file_path: str,
    engine: str = "whisper_local",
    model: str = "base",
    language: str = "",
    api_key: str = "",
    base_url: str = "",
) -> dict:
    """Transcribe and save result to analysis table.

    Returns dict with success/result/engine/transcript.
    """
    result, engine_label = transcribe_file(
        file_path, engine=engine, model=model,
        language=language, api_key=api_key, base_url=base_url,
    )

    analysis_result = _to_analysis_result(result)

    from core.services_core.audio_analysis_service import save_transcription_analysis

    save_transcription_analysis(file_id, engine_label, analysis_result)

    return {
        "success": True,
        "result": analysis_result.to_dict(),
        "engine": engine_label,
        "transcript": result,
    }
