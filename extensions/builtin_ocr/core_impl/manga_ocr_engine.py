"""manga-ocr engine (kha-white/manga-ocr-base).

Runs directly via transformers. Lazy load pattern same as WD-Tagger.
< 1GB model, so a daemon thread suffices (no separate process needed).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .types import OcrEngine, OcrRegion, OcrResult

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cached_engine: _MangaOcrWrapper | None = None


class _MangaOcrWrapper:
    """Wrapper for manga_ocr.MangaOcr. Thread-safe."""

    def __init__(self):
        self._model = None
        self._init_lock = threading.Lock()

    def ensure_loaded(self) -> bool:
        """Load the model. Returns True on success."""
        if self._model is not None:
            return True
        with self._init_lock:
            if self._model is not None:
                return True
            try:
                from manga_ocr import MangaOcr
                logger.info("manga-ocr: loading model...")
                self._model = MangaOcr()
                logger.info("manga-ocr: model loaded")
                return True
            except ImportError:
                logger.warning(
                    "manga-ocr is not installed. "
                    "Install: uv pip install manga-ocr"
                )
                return False
            except Exception as exc:
                logger.error("manga-ocr: failed to load: %s", exc)
                return False

    def predict(self, image_path: str) -> str:
        """Extract text from an image."""
        if not self.ensure_loaded():
            raise RuntimeError("manga-ocr model not available")
        return self._model(image_path)

    def unload(self):
        """Release the model."""
        self._model = None


def _get_wrapper() -> _MangaOcrWrapper:
    """Get the singleton MangaOcr wrapper."""
    global _cached_engine
    if _cached_engine is not None:
        return _cached_engine
    with _lock:
        if _cached_engine is not None:
            return _cached_engine
        _cached_engine = _MangaOcrWrapper()
        return _cached_engine


def clear_manga_ocr_cache():
    """Release the manga-ocr model."""
    global _cached_engine
    with _lock:
        if _cached_engine is not None:
            _cached_engine.unload()
            _cached_engine = None


def is_manga_ocr_available() -> bool:
    """Check if manga-ocr is available (does not load the model)."""
    try:
        import manga_ocr  # noqa: F401
        return True
    except ImportError:
        return False


class MangaOcrEngine(OcrEngine):
    """Manga-specialized OCR using manga-ocr (kha-white/manga-ocr-base).

    - 日本語漫画の縦書き・手書きフォントに特化
    - < 1GB の軽量モデル
    - 画像全体からテキストを抽出（bbox 検出は Phase 2c で別モデル追加予定）
    """

    def get_name(self) -> str:
        return "manga-ocr"

    def supports_task(self, task: str) -> bool:
        return task == "ocr_manga"

    def extract_text(self, image_path: Path, task: str = "ocr_manga",
                     language: str = "ja") -> OcrResult:
        wrapper = _get_wrapper()
        text = wrapper.predict(str(image_path))

        return OcrResult(
            engine="manga-ocr",
            task="ocr_manga",
            regions=[OcrRegion(
                region_id=1,
                text=text,
                confidence=0.95,
                direction="vertical",
                label="speech_bubble",
            )],
            full_text=text,
            language="ja",
        )
