"""3c: Video OCR -- keyframe extraction -> per-frame OCR -> merged results.

Leverages the existing video_keyframes module to extract text from video.
Audio transcription can optionally integrate with Hailo GenAI S2T.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .types import OcrEngine, OcrRegion, OcrResult

logger = logging.getLogger(__name__)


def ocr_video(
    engine: OcrEngine,
    video_path: Path,
    task: str = "ocr",
    language: str = "auto",
    keyframe_count: int = 4,
    strategy: str = "uniform",
    merge: bool = True,
) -> dict[str, Any]:
    """Run OCR on keyframes from a video.

    Args:
        engine: OCR engine
        video_path: 動画ファイルパス
        task: OCR タスク
        language: language hint
        keyframe_count: 抽出フレーム数
        strategy: "uniform" / "scene" / "single"
        merge: True なら全フレーム結果を統合

    Returns:
        { "frames": [...], "merged_text": str, "frame_count": int }
    """
    from core.files_core.video_keyframes import video_keyframes_context

    frame_results: list[dict[str, Any]] = []

    with video_keyframes_context(
        str(video_path),
        count=keyframe_count,
        strategy=strategy,
    ) as frames:
        if not frames:
            return {
                "frames": [],
                "merged_text": "",
                "frame_count": 0,
                "error": "No keyframes extracted (ffmpeg available?)",
            }

        for idx, frame_path in enumerate(frames):
            t0 = time.monotonic()
            try:
                result = engine.extract_text(frame_path, task=task, language=language)
                elapsed = int((time.monotonic() - t0) * 1000)
                frame_results.append({
                    "frame_index": idx,
                    "frame_path": str(frame_path),
                    "full_text": result.full_text,
                    "regions_count": len(result.regions),
                    "regions": [r.to_dict() for r in result.regions],
                    "language": result.language,
                    "elapsed_ms": elapsed,
                })
            except Exception as exc:
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.warning("OCR failed for frame %d: %s", idx, exc)
                frame_results.append({
                    "frame_index": idx,
                    "full_text": "",
                    "error": str(exc),
                    "elapsed_ms": elapsed,
                })

    # Merged results
    merged = ""
    if merge:
        merged = _merge_frame_texts(frame_results)

    return {
        "frames": frame_results,
        "merged_text": merged,
        "frame_count": len(frame_results),
    }


def _merge_frame_texts(frame_results: list[dict]) -> str:
    """Merge frame results. Remove duplicate text."""
    seen_texts = set()
    parts = []

    for fr in frame_results:
        text = fr.get("full_text", "").strip()
        if not text:
            continue
        # Deduplicate similar text (exact match only)
        normalized = text.lower().replace(" ", "").replace("\n", "")
        if normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        parts.append(text)

    return "\n\n---\n\n".join(parts)


def ocr_video_to_result(
    engine: OcrEngine,
    video_path: Path,
    file_id: int | None = None,
    task: str = "ocr",
    language: str = "auto",
    keyframe_count: int = 4,
    strategy: str = "uniform",
) -> OcrResult:
    """Convert video OCR results to OcrResult."""
    data = ocr_video(
        engine, video_path, task, language, keyframe_count, strategy,
    )

    regions = []
    for fr in data["frames"]:
        if fr.get("full_text"):
            regions.append(OcrRegion(
                region_id=fr["frame_index"] + 1,
                text=fr["full_text"],
                label=f"frame_{fr['frame_index']}",
            ))

    return OcrResult(
        file_id=file_id,
        engine=engine.get_name(),
        task=task,
        regions=regions,
        full_text=data["merged_text"],
        language=language,
    )


def extract_audio_text(
    video_path: Path,
    model: str = "",
) -> dict[str, Any] | None:
    """Transcribe video audio to text (Hailo S2T integration).

    Returns:
        { "text": str, "segments": [...] } or None
    """
    try:
        from core.files_core.video_audio import extract_audio_wav
    except ImportError:
        logger.info("video_audio module not available for audio extraction")
        return None

    try:
        import importlib.util
        from pathlib import Path
        # Load from the Hailo GenAI extension module by file path.
        _spec = importlib.util.spec_from_file_location(
            "hailo_genai_s2t_inference",
            Path(__file__).resolve().parents[2] / "builtin_hailo_genai" / "core_impl" / "s2t_inference.py")
        _s2t_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_s2t_mod)
        transcribe_audio = _s2t_mod.transcribe_audio
    except ImportError:
        logger.info("Hailo GenAI S2T not available for audio transcription")
        return None

    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            wav_path = extract_audio_wav(str(video_path), tmp.name)
            if not wav_path:
                return None
            result = transcribe_audio(wav_path, model=model)
            return result
    except Exception as exc:
        logger.warning("Audio transcription failed: %s", exc)
        return None


def is_video_file(path: Path) -> bool:
    """Determine if a file is a video."""
    VIDEO_EXTS = {".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv"}
    return path.suffix.lower() in VIDEO_EXTS
