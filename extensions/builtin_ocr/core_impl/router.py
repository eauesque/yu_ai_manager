"""OCR engine routing.

Selects an available server from the server registry
and returns it wrapped in VlmOcrEngine.
"""

from __future__ import annotations

import logging

from .manga_ocr_engine import MangaOcrEngine, is_manga_ocr_available
from .types import OcrEngine
from .vlm_ocr_engine import VlmOcrEngine

logger = logging.getLogger(__name__)


# Default capabilities template (ollama model prefix -> tasks)
_DEFAULT_CAPABILITIES = {
    "openbmb/minicpm-v4.5": {
        "ocr": 97, "ocr_document": 90, "ocr_manga": 70,
        "caption": 95, "tag": 93, "nsfw": 60,
    },
    "openbmb/minicpm-o4.5": {
        "ocr": 95, "ocr_document": 92, "ocr_manga": 65,
        "caption": 93, "tag": 90,
    },
    "huihui_ai/qwen2.5-vl-abliterated": {
        "ocr": 80, "ocr_document": 75, "ocr_manga": 50,
        "caption": 85, "tag": 85, "nsfw": 95,
    },
    "huihui_ai/qwen3-vl-abliterated": {
        "ocr": 85, "ocr_document": 80, "ocr_manga": 55,
        "caption": 88, "tag": 88, "nsfw": 95,
    },
    "qwen2.5vl": {
        "ocr": 80, "ocr_document": 78, "ocr_manga": 50,
        "caption": 85, "tag": 85,
    },
    "llama3.2-vision": {
        "ocr": 70, "ocr_document": 65, "ocr_manga": 30,
        "caption": 80, "tag": 78,
    },
}


def _get_model_score(model_tag: str, task: str) -> int:
    """Estimate task score from model tags.

    プロファイルシステムが利用可能ならそちらを優先し、
    フォールバックで _DEFAULT_CAPABILITIES を使う。
    """
    if not model_tag:
        return 50  # Unknown models default to 50
    tag_lower = model_tag.lower()

    # Search from profile system (built-in + local merged)
    try:
        from .profiles import load_profiles
        profiles = load_profiles()
        for prefix, scores in profiles.items():
            if prefix.lower() in tag_lower:
                return scores.get(task, 50)
    except Exception:
        logger.warning("OCR routing profiles were unreadable", exc_info=True)

    # Fallback: built-in defaults
    for prefix, scores in _DEFAULT_CAPABILITIES.items():
        if prefix.lower() in tag_lower:
            return scores.get(task, 50)
    return 50


class OcrRouter:
    """Select an engine based on OCR task."""

    def select_engine(
        self, task: str = "ocr",
        server_id: str | None = None,
    ) -> tuple[OcrEngine, str]:
        """Select the optimal OCR engine.

        Returns:
            (engine, error_message)
        """
        # Prefer manga-ocr if available for ocr_manga task
        if task == "ocr_manga" and not server_id and is_manga_ocr_available():
            logger.info("Using manga-ocr engine for ocr_manga task")
            return MangaOcrEngine(), ""

        try:
            engine, err = self._resolve_vlm(task, server_id)
            if err:
                return None, err
            return engine, ""
        except Exception as exc:
            logger.error("OCR engine resolution failed: %s", exc)
            return None, str(exc)

    def _resolve_vlm(
        self, task: str, server_id: str | None,
    ) -> tuple[OcrEngine | None, str]:
        """Select VLM from server registry based on score."""
        from core.analysis_api.server_registry import (
            get_all_servers,
            resolve_active_server,
        )
        from core.configuration.api import load_config_json

        config = load_config_json(None)

        if server_id:
            # Explicitly specified
            engine_type, kwargs, err = resolve_active_server(config, server_id=server_id)
            if err:
                return None, err
            return self._make_engine(engine_type, kwargs), ""

        # Select best server based on score
        servers = get_all_servers(config)
        if not servers:
            return None, "AI サーバーが登録されていません"

        # Calculate scores from model tags and sort
        scored = []
        for srv in servers:
            if not srv.enabled:
                continue
            model = srv.config.get("model", "")
            score = _get_model_score(model, task)
            scored.append((score, srv))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Try servers from highest score
        errors = []
        for _score, srv in scored:
            engine_type, kwargs, err = resolve_active_server(config, server_id=srv.id)
            if err:
                errors.append(f"{srv.name}: {err}")
                continue
            return self._make_engine(engine_type, kwargs), ""

        return None, "利用可能なサーバーがありません: " + "; ".join(errors)

    def _make_engine(self, engine_type: str, kwargs: dict) -> VlmOcrEngine:
        """Create an AnalysisEngine and wrap it in VlmOcrEngine."""
        from core.analysis.engines_factory import get_engine
        analysis_engine = get_engine(engine_type, **kwargs)
        return VlmOcrEngine(analysis_engine)


# Singleton
_router = OcrRouter()


def resolve_ocr_engine(
    task: str = "ocr", server_id: str | None = None,
) -> tuple[OcrEngine | None, str]:
    """Resolve an OCR engine. Convenience function."""
    return _router.select_engine(task, server_id)
