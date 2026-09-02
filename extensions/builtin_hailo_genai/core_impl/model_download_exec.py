"""Runtime HEF status and download helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.request import Request
from urllib.request import urlopen as _urlopen

logger = logging.getLogger(__name__)


def get_hef_path(model_name: str, genai_models, default_hef_dir: str, hef_dir: str | None = None) -> Path:
    hef_dir = hef_dir or default_hef_dir
    info = genai_models.get(model_name)
    if not info:
        raise ValueError(f"Unknown GenAI model: {model_name}")
    return Path(hef_dir) / info.hef_filename


def is_hef_available(model_name: str, genai_models, default_hef_dir: str, hef_dir: str | None = None) -> bool:
    try:
        return get_hef_path(model_name, genai_models, default_hef_dir, hef_dir).exists()
    except ValueError:
        return False


def get_model_status(genai_models, default_hef_dir: str, hef_dir: str | None = None) -> dict:
    result = {}
    for name, info in genai_models.items():
        path = get_hef_path(name, genai_models, default_hef_dir, hef_dir)
        result[name] = {
            "available": path.exists(),
            "path": str(path),
            "type": info.type.value,
            "description": info.description,
            "file_size_mb": round(path.stat().st_size / 1024 / 1024, 1) if path.exists() else None,
        }
    return result


def download_hef(model_name: str, genai_models, default_hef_dir: str, user_agent: str, hef_dir: str | None = None, progress_callback=None) -> Path:
    info = genai_models.get(model_name)
    if not info:
        raise ValueError(f"Unknown GenAI model: {model_name}")

    hef_dir = hef_dir or default_hef_dir
    os.makedirs(hef_dir, exist_ok=True)
    target = Path(hef_dir) / info.hef_filename
    if target.exists():
        logger.info("GenAI HEF already exists: %s", target)
        return target

    req = Request(info.url, headers={"User-Agent": user_agent})
    with _urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        tmp_path = target.with_suffix(".hef.tmp")
        with open(tmp_path, "wb") as handle:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total > 0:
                    progress_callback(downloaded, total)

    tmp_path.rename(target)
    logger.info("Downloaded GenAI model %s (%.1f MB)", target, target.stat().st_size / 1024 / 1024)
    return target
