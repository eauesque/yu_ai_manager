"""ONNX to Core ML model conversion and cache management.

Converts the CLIP ViT-B/16 ONNX vision model to a Core ML .mlpackage
for native Apple Neural Engine (ANE) execution.

The ONNX source is taken from ``cache/clip_onnx/`` if available, or
downloaded from HuggingFace. Converted models are cached at
``cache/clip_coreml/<repo>/vision_model.mlpackage``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_REPO = "Xenova/clip-vit-base-patch16"


def _clip_coreml_cache() -> Path:
    """Return the portable base directory for Core ML model cache."""
    from core.paths import cache_path
    return cache_path("clip_coreml")


def _clip_onnx_cache() -> Path:
    """Return the portable base directory for ONNX source cache."""
    from core.paths import cache_path
    return cache_path("clip_onnx")


def _safe_name(repo: str) -> str:
    """Convert repo name to safe directory name."""
    return re.sub(r"[^\w\-.]", "_", repo)


def get_coreml_dir(repo: str = _DEFAULT_REPO) -> Path:
    """Return the cache directory for the Core ML model."""
    return _clip_coreml_cache() / _safe_name(repo)


def get_coreml_model_path(repo: str = _DEFAULT_REPO) -> Path:
    """Return the expected path to the Core ML model package."""
    return get_coreml_dir(repo) / "vision_model.mlpackage"


def is_coreml_model_cached(repo: str = _DEFAULT_REPO) -> bool:
    """Check if the Core ML model already exists in cache."""
    mlpkg = get_coreml_model_path(repo)
    return mlpkg.exists() and mlpkg.is_dir()


def _get_onnx_source(repo: str) -> Path:
    """Locate the ONNX source model, downloading if necessary.

    Returns:
        Path to the ONNX model file.

    Raises:
        RuntimeError: If the model cannot be found or downloaded.
    """
    onnx_dir = _clip_onnx_cache() / _safe_name(repo)
    onnx_path = onnx_dir / "vision_model.onnx"

    if onnx_path.exists():
        return onnx_path

    # ONNX model not cached; try to download via the ONNX extension
    try:
        from core.clip_onnx_core.model_download import download_model
        downloaded = download_model(repo)
        logger.info("Downloaded ONNX model for CoreML conversion: %s", downloaded)
        return downloaded
    except Exception as exc:
        raise RuntimeError(
            f"ONNX source model not available for CoreML conversion. "
            f"Download it first via the ONNX model download API. ({exc})"
        ) from exc


def convert_onnx_to_coreml(repo: str = _DEFAULT_REPO) -> Path:
    """Convert the ONNX CLIP vision model to Core ML format.

    Args:
        repo: HuggingFace repo ID for the source model.

    Returns:
        Path to the saved .mlpackage directory.

    Raises:
        RuntimeError: If conversion fails.
    """
    import coremltools as ct

    onnx_path = _get_onnx_source(repo)
    output_path = get_coreml_model_path(repo)

    if is_coreml_model_cached(repo):
        logger.info("Core ML model already cached: %s", output_path)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Converting ONNX -> Core ML: %s", onnx_path)
    try:
        ml_model = ct.convert(
            str(onnx_path),
            convert_to="mlprogram",
            minimum_deployment_target=ct.target.macOS13,
            compute_precision=ct.precision.FLOAT32,
        )
        ml_model.save(str(output_path))
        logger.info("Core ML model saved: %s", output_path)
    except Exception as exc:
        # Clean up partial output
        import shutil
        if output_path.exists():
            shutil.rmtree(output_path, ignore_errors=True)
        raise RuntimeError(
            f"Failed to convert ONNX model to Core ML: {exc}"
        ) from exc

    return output_path


def ensure_coreml_model(repo: str = _DEFAULT_REPO) -> Path:
    """Ensure the Core ML model is available, converting if needed.

    This is the main entry point called lazily on first encoder init.

    Returns:
        Path to the .mlpackage directory.
    """
    if is_coreml_model_cached(repo):
        return get_coreml_model_path(repo)
    return convert_onnx_to_coreml(repo)
