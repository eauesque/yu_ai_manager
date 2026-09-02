"""ONNX-based WD-Tagger inference engine.

Loads a WD-Tagger ONNX model and runs local inference.
Requires: onnxruntime (or onnxruntime-gpu / onnxruntime-directml), numpy, Pillow

GPU acceleration is auto-detected. Install the appropriate package:
  - NVIDIA CUDA:  pip install onnxruntime-gpu
  - AMD ROCm:     pip install onnxruntime-rocm
  - Windows GPU:  pip install onnxruntime-directml
  - CPU only:     pip install onnxruntime
"""

from __future__ import annotations

import logging
from pathlib import Path

from .types import TagPrediction, WdTaggerEngine, WdTagResult

logger = logging.getLogger(__name__)

# Default input size for WD-Tagger models
_INPUT_SIZE = 448

# Default confidence thresholds
_DEFAULT_GENERAL_THRESHOLD = 0.35
_DEFAULT_CHARACTER_THRESHOLD = 0.85

def _select_providers() -> list[str]:
    """Return available ORT providers in priority order.

    core.inference_core.ort_provider に委譲する。
    """
    from importlib import import_module
    _ort_mod = import_module("extensions.builtin_inference.core_impl.ort_provider")
    select_providers = _ort_mod.select_providers

    return select_providers()


def _preprocess_image(image_path: str, size: int = _INPUT_SIZE):
    """Load and preprocess image for WD-Tagger inference.

    Resize with aspect ratio preservation + white padding,
    convert RGB -> BGR, normalize to float32 [0, 1].
    """
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as _raw_img:
        img = _raw_img.convert("RGBA")

    # Composite onto white background (handle transparency)
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    # Resize with aspect ratio preservation
    old_w, old_h = img.size
    scale = size / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Pad to square with white
    padded = Image.new("RGB", (size, size), (255, 255, 255))
    padded.paste(img, ((size - new_w) // 2, (size - new_h) // 2))

    # Convert to numpy: HWC, float32, RGB->BGR
    arr = np.array(padded, dtype=np.float32)
    arr = arr[:, :, ::-1]  # RGB -> BGR

    # Add batch dimension: (1, H, W, C)
    return np.expand_dims(arr, axis=0)


class OnnxWdTaggerEngine(WdTaggerEngine):
    """Local ONNX inference engine for WD-Tagger models."""

    def __init__(
        self,
        model_dir: Path,
        general_threshold: float = _DEFAULT_GENERAL_THRESHOLD,
        character_threshold: float = _DEFAULT_CHARACTER_THRESHOLD,
    ):
        self._model_dir = Path(model_dir)
        self._general_threshold = general_threshold
        self._character_threshold = character_threshold
        self._session: object | None = None
        self._tag_names: list = []
        self._categories: list = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load ONNX model and tags CSV."""
        if self._loaded:
            return

        from .tag_csv import parse_tags_csv

        model_path = self._model_dir / "model.onnx"
        csv_path = self._model_dir / "selected_tags.csv"

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        if not csv_path.exists():
            raise FileNotFoundError(f"Tags CSV not found: {csv_path}")

        # _select_providers registers DLL dirs then imports onnxruntime
        providers = _select_providers()

        import onnxruntime as ort

        logger.info(
            "Loading ONNX model from %s (providers: %s)",
            model_path,
            providers,
        )
        self._session = ort.InferenceSession(
            str(model_path),
            providers=providers,
        )
        active = self._session.get_providers()
        logger.info("ONNX session active providers: %s", active)
        try:
            from extensions.builtin_inference.core_impl.ort_provider import register_active_session
            register_active_session("wd_tagger", self._session, model_path)
        except Exception:
            logger.debug("ORT session registry update failed", exc_info=True)

        self._tag_names, self._categories = parse_tags_csv(csv_path)
        self._loaded = True
        logger.info("WD-Tagger ONNX engine ready (%d tags)", len(self._tag_names))

    def _build_result(self, probs) -> WdTagResult:
        """Build WdTagResult from probability array (shared by tag_image / tag_images_batch)."""
        tags = []
        rating_label = "general"
        rating_max = 0.0

        for i, (name, category) in enumerate(zip(self._tag_names, self._categories, strict=False)):
            if i >= len(probs):
                break
            conf = float(probs[i])

            if category == "rating":
                if conf > rating_max:
                    rating_max = conf
                    rating_label = name
                continue

            # Apply category-specific thresholds
            threshold = self._character_threshold if category == "character" else self._general_threshold
            if conf >= threshold:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=round(conf, 4),
                    category=category,
                ))

        # Sort by confidence descending
        tags.sort(key=lambda t: t.confidence, reverse=True)

        return WdTagResult(
            tags=tags,
            model=self._model_dir.name,
            rating=rating_label,
        )

    def tag_image(self, image_path: str) -> WdTagResult:
        """Run inference on a single image."""
        self._ensure_loaded()

        input_data = _preprocess_image(image_path)
        input_name = self._session.get_inputs()[0].name
        output = self._session.run(None, {input_name: input_data})

        # Output shape: (1, num_tags)
        probs = output[0][0]
        return self._build_result(probs)

    def tag_images_batch(
        self, filepaths: list[str], batch_size: int = 8,
    ) -> list[WdTagResult | None]:
        """Batch inference for multiple images. Reduces GPU transfer overhead.

        Args:
            filepaths: List of image paths for inference
            batch_size: Number of images per ONNX session.run call (default 8)

        Returns:
            List of same length as filepaths. None on preprocessing failure.
        """
        import numpy as np

        self._ensure_loaded()

        input_name = self._session.get_inputs()[0].name
        results: list[WdTagResult | None] = []

        for chunk_start in range(0, len(filepaths), batch_size):
            chunk_paths = filepaths[chunk_start:chunk_start + batch_size]

            # Preprocessing: _preprocess_image each image individually, collect valid ones
            preprocessed: list = []
            valid_indices: list[int] = []
            for j, fp in enumerate(chunk_paths):
                try:
                    tensor = _preprocess_image(fp)  # (1, H, W, C)
                    preprocessed.append(tensor)
                    valid_indices.append(j)
                except Exception as exc:
                    logger.debug("Batch preprocess failed for %s: %s", fp, exc)

            # Prepare result slots for each image in chunk (None-filled)
            chunk_results: list[WdTagResult | None] = [None] * len(chunk_paths)

            if preprocessed:
                # Build (N, H, W, C) batch tensor
                batch_input = np.concatenate(preprocessed, axis=0)

                # Batch inference
                batch_output = self._session.run(
                    None, {input_name: batch_input},
                )[0]  # shape: (N, num_tags)

                # Split results individually and build WdTagResult
                for idx_in_valid, global_idx in enumerate(valid_indices):
                    chunk_results[global_idx] = self._build_result(
                        batch_output[idx_in_valid],
                    )

            results.extend(chunk_results)

        return results

    def get_name(self) -> str:
        return f"ONNX ({self._model_dir.name})"

    def is_available(self) -> bool:
        model_path = self._model_dir / "model.onnx"
        csv_path = self._model_dir / "selected_tags.csv"
        return model_path.exists() and csv_path.exists()
