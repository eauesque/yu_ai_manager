"""Hailo-10H NPU backend for Speech-to-Text.

Wraps the existing hailo_platform.genai.Speech2Text via device_manager.
"""

import logging
import sys

import numpy as np

from .base import S2TBackend

logger = logging.getLogger(__name__)


def _load_hailo_genai_helpers() -> tuple:
    """Load get_hef_path and is_hef_available from builtin-hailo-genai.

    Uses importlib to cross-reference the sibling extension.
    Registers the parent package in sys.modules so that relative
    imports inside model_download.py work correctly.
    """
    import importlib.util
    from pathlib import Path

    genai_core = Path(__file__).resolve().parents[2] / "builtin_hailo_genai" / "core_impl"
    pkg_name = "hailo_genai_core_impl"

    # Ensure the parent package is registered so relative imports work
    if pkg_name not in sys.modules:
        init_path = genai_core / "__init__.py"
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name, str(init_path),
            submodule_search_locations=[str(genai_core)],
        )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg_mod
        if pkg_spec.loader:
            pkg_spec.loader.exec_module(pkg_mod)

    # Load genai_types first (dependency of model_download)
    types_name = f"{pkg_name}.genai_types"
    if types_name not in sys.modules:
        types_spec = importlib.util.spec_from_file_location(
            types_name, str(genai_core / "genai_types.py"),
        )
        types_mod = importlib.util.module_from_spec(types_spec)
        sys.modules[types_name] = types_mod
        types_spec.loader.exec_module(types_mod)

    # Load model_download
    dl_name = f"{pkg_name}.model_download"
    if dl_name not in sys.modules:
        dl_spec = importlib.util.spec_from_file_location(
            dl_name, str(genai_core / "model_download.py"),
        )
        dl_mod = importlib.util.module_from_spec(dl_spec)
        sys.modules[dl_name] = dl_mod
        dl_spec.loader.exec_module(dl_mod)

    dl_mod = sys.modules[dl_name]
    return dl_mod.get_hef_path, dl_mod.is_hef_available


class HailoS2TBackend(S2TBackend):
    """Hailo-10H NPU backend (highest priority)."""

    name = "hailo"

    def __init__(self):
        self._s2t = None
        self._model_size = ""

    @staticmethod
    def is_available() -> bool:
        try:
            from hailo_platform.genai import Speech2Text  # noqa: F401

            from core.hailo_device_core.device_manager import is_hailo_available
            return is_hailo_available()
        except (ImportError, Exception):
            return False

    @staticmethod
    def priority() -> int:
        return 100

    def load_model(self, model_size: str) -> None:
        if self._s2t is not None and self._model_size == model_size:
            return
        self.close()

        from hailo_platform.genai import Speech2Text

        from core.hailo_device_core.device_manager import acquire_genai

        model_name = f"whisper-{model_size}"
        get_hef_path, is_hef_available = _load_hailo_genai_helpers()
        if not is_hef_available(model_name):
            raise RuntimeError(
                f"Hailo HEF model '{model_name}' not downloaded. "
                f"Use the GenAI extension to download it first."
            )
        path = str(get_hef_path(model_name))
        self._s2t = acquire_genai("s2t", path, lambda vd, p: Speech2Text(vd, p))
        self._model_size = model_size
        logger.info("Hailo S2T backend loaded: %s", model_name)

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: str = "en",
    ) -> list[dict]:
        if self._s2t is None:
            raise RuntimeError("Model not loaded")

        # Check whether device-manager ownership changed since this instance loaded.
        from core.hailo_device_core.device_manager import is_model_active
        if not is_model_active("s2t"):
            logger.warning("S2T model was evicted externally; reloading")
            self.load_model(self._model_size)

        from hailo_platform.genai import Speech2TextTask

        audio = _ensure_le_float32(audio_data)
        segments = self._s2t.generate_all_segments(
            audio_data=audio,
            task=Speech2TextTask.TRANSCRIBE,
            language=language,
            timeout_ms=120000,
        )
        result = []
        for seg in segments:
            # SegmentInfo on hailort 5.3.0 exposes: text, start_sec, end_sec.
            # Keep legacy-name fallbacks in case Hailo renames again.
            text = getattr(seg, "text", "")
            start = (
                getattr(seg, "start_sec", None)
                if hasattr(seg, "start_sec")
                else getattr(seg, "start", None)
                or getattr(seg, "start_time", None)
            )
            end = (
                getattr(seg, "end_sec", None)
                if hasattr(seg, "end_sec")
                else getattr(seg, "end", None)
                or getattr(seg, "end_time", None)
            )
            if start is None or end is None:
                logger.warning("SegmentInfo attrs: %s", dir(seg))
                start = start if start is not None else 0.0
                end = end if end is not None else 0.0
            result.append({"text": text, "start": start, "end": end})
        return result

    @staticmethod
    def cached_models() -> list:
        """Detect locally available Hailo HEF Whisper models."""
        results = []
        try:
            get_hef_path, is_hef_available = _load_hailo_genai_helpers()
        except (ImportError, Exception):
            return results

        for size in ("tiny", "base", "small", "medium"):
            model_name = f"whisper-{size}"
            try:
                if is_hef_available(model_name):
                    path = get_hef_path(model_name)
                    size_bytes = path.stat().st_size if path.is_file() else 0
                    results.append({
                        "size": size,
                        "path": str(path),
                        "size_bytes": size_bytes,
                    })
            except Exception:
                logger.debug("HEF probe failed", exc_info=True)
        return results

    def close(self) -> None:
        if self._s2t is not None:
            try:
                from core.hailo_device_core.device_manager import release_device
                release_device("s2t")
            except Exception:
                logger.warning("hailo device was not released", exc_info=True)
            self._s2t = None
            self._model_size = ""


def _ensure_le_float32(audio: np.ndarray) -> np.ndarray:
    """Convert audio to little-endian float32 normalised to [-1, 1]."""
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    return audio.astype("<f4")
