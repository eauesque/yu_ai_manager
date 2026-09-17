"""Legacy repo-string model download API."""

from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{file}"
LEGACY_DEFAULT_FILES: tuple[str, ...] = ("model.onnx", "selected_tags.csv")
USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger downloader)"


def wd_tagger_cache() -> Path:
    from core.paths import cache_path

    return cache_path("wd_tagger")


def safe_name(repo: str) -> str:
    return re.sub(r"[^\w\-.]", "_", repo)


def get_model_dir(repo: str) -> Path:
    return wd_tagger_cache() / safe_name(repo)


def is_model_downloaded(repo: str) -> bool:
    model_dir = get_model_dir(repo)
    return all((model_dir / file_name).exists() for file_name in LEGACY_DEFAULT_FILES)


def get_model_status(repo: str) -> dict:
    model_dir = get_model_dir(repo)
    files: dict[str, dict] = {}
    for file_name in LEGACY_DEFAULT_FILES:
        path = model_dir / file_name
        files[file_name] = (
            {"exists": True, "size_mb": round(path.stat().st_size / (1024 * 1024), 2)}
            if path.exists()
            else {"exists": False, "size_mb": 0}
        )
    return {
        "repo": repo,
        "ready": is_model_downloaded(repo),
        "cache_dir": str(model_dir),
        "files": files,
    }


def download_model(repo: str, progress_callback=None) -> Path:
    model_dir = get_model_dir(repo)
    model_dir.mkdir(parents=True, exist_ok=True)
    for file_name in LEGACY_DEFAULT_FILES:
        _download_legacy_file(repo, model_dir, file_name, progress_callback)
    return model_dir


def _download_legacy_file(repo: str, model_dir: Path, file_name: str, progress_callback) -> None:
    dest = model_dir / file_name
    if dest.exists():
        return
    url = HF_RESOLVE.format(repo=repo, file=file_name)
    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp:
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
                        progress_callback(file_name, downloaded, total)
        os.replace(tmp_dest, dest)
    except Exception as exc:
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise RuntimeError(f"Failed to download {file_name} from {repo}: {exc}") from exc
