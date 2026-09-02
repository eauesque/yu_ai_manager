"""Download CLIP ONNX vision model from HuggingFace.

Fetches ``onnx/vision_model.onnx`` from ``Xenova/clip-vit-base-patch16``.
Follows the same pattern as ``core.wd_tagger_core.model_download``.
"""

from __future__ import annotations

import logging
import re
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{file}"
_USER_AGENT = "YU-AI-Manager/2.0 (CLIP-ONNX downloader)"

# Default model repo and file
_DEFAULT_REPO = "Xenova/clip-vit-base-patch16"
_MODEL_FILE = "onnx/vision_model.onnx"

def _clip_onnx_cache() -> Path:
    """Return the portable base directory for CLIP ONNX model cache."""
    from core.paths import cache_path
    return cache_path("clip_onnx")


def _legacy_clip_onnx_cache() -> Path:
    """Return the pre-path-refactor CLIP ONNX cache directory."""
    return Path.home() / ".cache" / "yu_ai_manager" / "clip_onnx"


def _safe_name(repo: str) -> str:
    """Convert repo name to safe directory name."""
    return re.sub(r"[^\w\-.]", "_", repo)


def get_model_dir(repo: str = _DEFAULT_REPO) -> Path:
    """Return the cache directory for a given model repo."""
    return _clip_onnx_cache() / _safe_name(repo)


def get_model_path(repo: str = _DEFAULT_REPO) -> Path:
    """Return the expected path to the ONNX model file."""
    return get_model_dir(repo) / "vision_model.onnx"


def get_legacy_model_path(repo: str = _DEFAULT_REPO) -> Path:
    """Return the legacy cache path used before core.paths unification."""
    return _legacy_clip_onnx_cache() / _safe_name(repo) / "vision_model.onnx"


def resolve_existing_model_path(repo: str = _DEFAULT_REPO) -> Path | None:
    """Return the first existing model path across current and legacy caches."""
    primary = get_model_path(repo)
    if primary.exists():
        return primary
    legacy = get_legacy_model_path(repo)
    if legacy.exists():
        return legacy
    return None


def is_model_downloaded(repo: str = _DEFAULT_REPO) -> bool:
    """Check if the ONNX model file exists in cache."""
    return resolve_existing_model_path(repo) is not None


def get_model_status(repo: str = _DEFAULT_REPO) -> dict:
    """Return download status for the CLIP ONNX model."""
    model_path = resolve_existing_model_path(repo)
    if model_path is not None:
        size_mb = round(model_path.stat().st_size / (1024 * 1024), 2)
        return {
            "repo": repo,
            "ready": True,
            "path": str(model_path),
            "size_mb": size_mb,
        }
    expected_path = get_model_path(repo)
    return {
        "repo": repo,
        "ready": False,
        "path": str(expected_path),
        "size_mb": 0,
    }


def download_model(
    repo: str = _DEFAULT_REPO,
    progress_callback: callable | None = None,
) -> Path:
    """Download the CLIP ONNX vision model from HuggingFace.

    Args:
        repo: HuggingFace repo ID.
        progress_callback: Optional callback(file_name, bytes_downloaded, total_bytes).

    Returns:
        Path to the downloaded model file.

    Raises:
        RuntimeError: If download fails.
    """
    model_dir = get_model_dir(repo)
    model_dir.mkdir(parents=True, exist_ok=True)

    existing = resolve_existing_model_path(repo)
    if existing is not None:
        logger.info("CLIP ONNX model already cached: %s", existing)
        return existing

    dest = get_model_path(repo)

    url = _HF_RESOLVE.format(repo=repo, file=_MODEL_FILE)
    logger.info("Downloading CLIP ONNX model from %s", url)

    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_dest, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)  # 256KB chunks
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback("vision_model.onnx", downloaded, total)

        tmp_dest.rename(dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        logger.info("Downloaded CLIP ONNX model (%.1f MB)", size_mb)

    except Exception as exc:
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise RuntimeError(
            f"Failed to download CLIP ONNX model from {repo}: {exc}"
        ) from exc

    return dest
