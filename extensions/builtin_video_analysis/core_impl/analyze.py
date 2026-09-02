"""Video analysis orchestrator.

Extracts keyframes, sends to vision LLM, parses and saves results.
"""

import logging
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


def _get_analysis_imports():
    """Import AnalysisResult and parse_image_analysis from builtin_analysis."""
    _ensure_analysis_path()
    from core_impl.engines_claude_parse import parse_image_analysis
    from core_impl.types import AnalysisResult
    return AnalysisResult, parse_image_analysis


def _resolve_engine(ai_config: dict, engine_override: str = "", model_override: str = ""):
    """Resolve which vision engine to use.

    Returns (engine_type, engine_kwargs) or raises RuntimeError.
    """
    from core.analysis_api.single_ops import _resolve_override, _resolve_with_fallback

    if engine_override:
        engine_type, kwargs, err = _resolve_override(ai_config, engine_override, model_override or None)
    else:
        engine_type, kwargs, err = _resolve_with_fallback(ai_config)

    if err:
        raise RuntimeError(err)

    return engine_type, kwargs


def analyze_video_frames(
    frames: list[Path],
    engine_type: str,
    engine_kwargs: dict,
    language: str = "ja",
) -> tuple[str, str]:
    """Send multiple keyframes to a vision LLM and get holistic analysis.

    Returns (raw_response, engine_label).
    """
    from .multi_frame import (
        build_claude_messages,
        build_ollama_messages,
        build_openai_messages,
    )

    # Import engine implementations from builtin_analysis
    _ensure_analysis_path()
    from core_impl.engines_claude import ClaudeVisionEngine
    from core_impl.engines_ollama import OllamaVisionEngine
    from core_impl.engines_openai import OpenAIVisionEngine

    if engine_type == "claude_api":
        messages, system = build_claude_messages(frames, language)
        eng = ClaudeVisionEngine(
            api_key=engine_kwargs.get("api_key", ""),
            model=engine_kwargs.get("model", "claude-sonnet-4-6"),
            language=language,
        )
        raw = eng._call_api(messages, system=system)
        label = f"Video Analysis ({eng.model})"

    elif engine_type in ("openai", "openai_compat"):
        eng = OpenAIVisionEngine(
            api_key=engine_kwargs.get("api_key", ""),
            model=engine_kwargs.get("model", "gpt-4o-mini"),
            base_url=engine_kwargs.get("base_url", ""),
            language=language,
        )
        messages = build_openai_messages(frames, language)
        raw = eng._call_api(messages)
        label = f"Video Analysis ({eng.model})"

    elif engine_type == "ollama":
        eng = OllamaVisionEngine(
            base_url=engine_kwargs.get("base_url", "http://localhost:11434"),
            model=engine_kwargs.get("model", "llava:latest"),
            language=language,
        )
        messages = build_ollama_messages(frames, language)
        raw = eng._call_api(messages)
        label = f"Video Analysis ({eng.model})"

    else:
        raise RuntimeError(f"Unsupported engine for video analysis: {engine_type}")

    return raw, label


def analyze_and_save(
    file_id: int,
    file_path: str,
    engine_override: str = "",
    model_override: str = "",
    keyframe_count: int = 4,
    strategy: str = "uniform",
) -> dict:
    """Extract keyframes, analyze, and save to analysis table.

    Returns dict with success/result/engine.
    """
    from core.configuration.json_rw import load_config_json
    from core.files_core.video_keyframes import video_keyframes_context
    from core.services_core.db_write import submit_db_write

    AnalysisResult, parse_image_analysis = _get_analysis_imports()

    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})
    language = ai_config.get("language", "ja")

    engine_type, engine_kwargs = _resolve_engine(ai_config, engine_override, model_override)

    with video_keyframes_context(
        file_path,
        count=keyframe_count,
        strategy=strategy,
    ) as frames:
        if not frames:
            raise RuntimeError("Failed to extract keyframes from video")

        logger.info(
            "Video analysis: %d frames, engine=%s, file_id=%d",
            len(frames), engine_type, file_id,
        )

        raw, engine_label = analyze_video_frames(
            frames, engine_type, engine_kwargs, language,
        )

    # Parse response
    result = parse_image_analysis(raw)

    # Save to analysis table
    from core.services_core.video_analysis_service import save_video_analysis

    def _write() -> None:
        save_video_analysis(file_id, engine_label, result)

    submit_db_write(_write)

    return {
        "success": True,
        "result": result.to_dict(),
        "engine": engine_label,
    }
