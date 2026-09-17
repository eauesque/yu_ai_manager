"""Download CLIP ONNX text model + tokenizer from HuggingFace.

Mirrors :mod:`extensions.builtin_clip_onnx.core_impl.model_download` (which
handles the vision side) — fetches ``onnx/text_model.onnx`` and
``tokenizer.json`` from ``Xenova/clip-vit-base-patch16``. Cached under the
same ``clip_onnx/<repo_safe>/`` directory the vision model uses.

The Xenova export bakes ``text_projection`` into ``text_model.onnx``, so the
single output is the 512-dim text embedding (matches ``vision_model.onnx``).
"""

from __future__ import annotations

import logging
import re
import urllib.request
from pathlib import Path

from .model_download import resolve_clip_model_dir

logger = logging.getLogger(__name__)

_HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{file}"
_USER_AGENT = "YU-AI-Manager/2.0 (CLIP-ONNX text downloader)"

_DEFAULT_REPO = "Xenova/clip-vit-base-patch16"
_TEXT_MODEL_FILE = "onnx/text_model.onnx"
_TOKENIZER_FILE = "tokenizer.json"


def _clip_onnx_cache() -> Path:
    """Return the portable base directory for CLIP ONNX model cache."""
    from core.paths import cache_path
    return cache_path("clip_onnx")


def _safe_name(repo: str) -> str:
    return re.sub(r"[^\w\-.]", "_", repo)


def get_model_dir(repo: str = _DEFAULT_REPO) -> Path:
    return _clip_onnx_cache() / _safe_name(repo)


def get_text_model_path(repo: str = _DEFAULT_REPO) -> Path:
    return get_model_dir(repo) / "text_model.onnx"


def get_tokenizer_path(repo: str = _DEFAULT_REPO) -> Path:
    return get_model_dir(repo) / "tokenizer.json"


# Single-normalization rule (S1/S3): resolve the shared directory once via
# model_download.py's resolve_clip_model_dir() rather than re-deriving a
# primary-vs-legacy pick here, so text/tokenizer resolution can never diverge
# from the vision side's file-count majority vote.
def resolve_existing_text_model_path(repo: str = _DEFAULT_REPO) -> Path | None:
    path = resolve_clip_model_dir(repo) / "text_model.onnx"
    return path if path.exists() else None


def resolve_existing_tokenizer_path(repo: str = _DEFAULT_REPO) -> Path | None:
    path = resolve_clip_model_dir(repo) / "tokenizer.json"
    return path if path.exists() else None


def is_text_model_downloaded(repo: str = _DEFAULT_REPO) -> bool:
    return (
        resolve_existing_text_model_path(repo) is not None
        and resolve_existing_tokenizer_path(repo) is not None
    )


def get_text_model_status(repo: str = _DEFAULT_REPO) -> dict:
    """Return download status for the CLIP ONNX text model + tokenizer."""
    model_path = resolve_existing_text_model_path(repo)
    tok_path = resolve_existing_tokenizer_path(repo)
    ready = model_path is not None and tok_path is not None
    size_mb = 0.0
    if model_path is not None:
        size_mb = round(model_path.stat().st_size / (1024 * 1024), 2)
    return {
        "repo": repo,
        "ready": ready,
        "path": str(model_path) if model_path else str(get_text_model_path(repo)),
        "tokenizer_path": str(tok_path) if tok_path else str(get_tokenizer_path(repo)),
        "size_mb": size_mb,
    }


def _download_one(url: str, dest: Path, label: str, progress_callback=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_dest, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(label, downloaded, total)
        tmp_dest.rename(dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        logger.info("Downloaded %s (%.1f MB)", label, size_mb)
    except Exception as exc:
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise RuntimeError(f"Failed to download {label}: {exc}") from exc


def download_text_model(
    repo: str = _DEFAULT_REPO,
    progress_callback=None,
) -> tuple[Path, Path]:
    """Download the CLIP ONNX text model and tokenizer.

    Returns:
        ``(model_path, tokenizer_path)`` as :class:`Path` objects.
    """
    existing_model = resolve_existing_text_model_path(repo)
    existing_tok = resolve_existing_tokenizer_path(repo)
    if existing_model is not None and existing_tok is not None:
        logger.info("CLIP ONNX text model already cached: %s", existing_model)
        return existing_model, existing_tok

    model_dest = get_text_model_path(repo)
    tok_dest = get_tokenizer_path(repo)

    if existing_model is None:
        url = _HF_RESOLVE.format(repo=repo, file=_TEXT_MODEL_FILE)
        logger.info("Downloading CLIP ONNX text model from %s", url)
        _download_one(url, model_dest, "text_model.onnx", progress_callback)
    else:
        model_dest = existing_model

    if existing_tok is None:
        url = _HF_RESOLVE.format(repo=repo, file=_TOKENIZER_FILE)
        logger.info("Downloading CLIP %s from %s", _TOKENIZER_FILE, url)
        _download_one(url, tok_dest, "tokenizer.json", progress_callback)
    else:
        tok_dest = existing_tok

    return model_dest, tok_dest
