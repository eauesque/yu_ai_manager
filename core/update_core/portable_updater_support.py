"""Support helpers for portable ZIP updates."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from core.update_core.detect import PROJECT_ROOT

logger = logging.getLogger(__name__)

_GITHUB_REPO = "eauesque/yu_ai_manager"
_RELEASES_URL = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_PRESERVE = {"data", "config.json", "uploads", "cache", "python", "_old_version", "venv", "data_backup"}


def read_version() -> str:
    """Read current version from VERSION file."""
    try:
        with open(os.path.join(PROJECT_ROOT, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return "0.0.0"


def resolve_latest_download(old_version: str) -> tuple[str | None, str, str | None]:
    """Resolve the latest portable ZIP download URL, version, and digest."""
    req = urllib.request.Request(
        _RELEASES_URL,
        headers={
            "User-Agent": f"YU-AI-Manager/{old_version}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        release_data = json.loads(resp.read().decode("utf-8"))

    tag = release_data.get("tag_name", "")
    new_version = tag.lstrip("v")
    asset = find_portable_asset(release_data.get("assets", []))
    digest = _extract_sha256_digest(asset) if asset else None
    return (asset.get("browser_download_url") if asset else None, new_version, digest)


def find_portable_asset(assets: list[dict]) -> dict | None:
    """Find the portable Windows amd64 ZIP asset from release assets."""
    for asset in assets:
        name = asset.get("name", "").lower()
        if "portable" in name and "win" in name and "amd64" in name and name.endswith(".zip"):
            return asset
    return None


def download_asset(
    url: str,
    version: str,
    emit_progress: Callable[[str, str, str], None],
    expected_sha256: str | None = None,
) -> str:
    """Download an asset to a temp file and return the local path."""
    tmp_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="yu_update_")
    os.close(tmp_fd)
    sha256 = hashlib.sha256()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"YU-AI-Manager/{version}",
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 256 * 1024
        with open(zip_path, "wb") as handle:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                if expected_sha256:
                    sha256.update(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded * 100 / total)
                    emit_progress(
                        "download",
                        "running",
                        f"{pct}% ({downloaded / (1024 * 1024):.1f}/{total / (1024 * 1024):.1f} MB)",
                    )
    if expected_sha256 and sha256.hexdigest().lower() != expected_sha256.lower():
        with contextlib.suppress(OSError):
            os.remove(zip_path)
        raise ValueError("Downloaded asset digest mismatch")
    return zip_path


def create_backup() -> str:
    """Back up persistent user data and return the backup directory path."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(PROJECT_ROOT, f"data_backup_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)

    _copy_if_dir(os.path.join(PROJECT_ROOT, "data"), os.path.join(backup_dir, "data"))
    _copy_if_file(os.path.join(PROJECT_ROOT, "config.toml"), os.path.join(backup_dir, "config.toml"))
    _copy_if_file(os.path.join(PROJECT_ROOT, "config.json"), os.path.join(backup_dir, "config.json"))
    _copy_if_dir(os.path.join(PROJECT_ROOT, "uploads"), os.path.join(backup_dir, "uploads"))
    return backup_dir


def extract_zip(zip_path: str) -> tuple[str, str]:
    """Extract ZIP and return (extract_dir, source_dir)."""
    extract_dir = tempfile.mkdtemp(prefix="yu_update_extract_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        _validate_zip_members(zf, extract_dir)
        zf.extractall(extract_dir)

    top_entries = os.listdir(extract_dir)
    if len(top_entries) == 1 and os.path.isdir(os.path.join(extract_dir, top_entries[0])):
        return extract_dir, os.path.join(extract_dir, top_entries[0])
    return extract_dir, extract_dir


def _validate_zip_members(zf: zipfile.ZipFile, extract_dir: str) -> None:
    """Reject ZIP entries that would escape the extraction directory."""
    base_dir = Path(extract_dir).resolve()
    for info in zf.infolist():
        target = (base_dir / info.filename).resolve()
        if target != base_dir and base_dir not in target.parents:
            raise ValueError(f"ZIP slip detected: {info.filename}")


def _extract_sha256_digest(asset: dict | None) -> str | None:
    """Extract a sha256 hex digest from a GitHub release asset payload."""
    if not asset:
        return None
    raw = str(asset.get("digest") or "").strip()
    if not raw:
        return None
    if ":" in raw:
        algo, value = raw.split(":", 1)
        if algo.lower() != "sha256":
            raise ValueError(f"Unsupported asset digest algorithm: {algo}")
        raw = value
    digest = raw.strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("Invalid asset digest format")
    return digest


def replace_project_files(source_dir: str, backup_dir: str) -> None:
    """Replace app files while preserving persistent user data."""
    old_dir = os.path.join(PROJECT_ROOT, "_old_version")
    if os.path.exists(old_dir):
        shutil.rmtree(old_dir, ignore_errors=True)
    os.makedirs(old_dir, exist_ok=True)

    for entry in os.listdir(PROJECT_ROOT):
        if should_preserve(entry):
            continue
        src = os.path.join(PROJECT_ROOT, entry)
        dst = os.path.join(old_dir, entry)
        try:
            shutil.move(src, dst)
        except Exception as exc:
            logger.warning("Could not move %s to _old_version: %s", entry, exc)

    for entry in os.listdir(source_dir):
        if should_preserve(entry):
            continue
        src = os.path.join(source_dir, entry)
        dst = os.path.join(PROJECT_ROOT, entry)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        except Exception as exc:
            logger.warning("Could not copy %s from new version: %s", entry, exc)

    restore_backup(backup_dir)


def restore_backup(backup_dir: str) -> None:
    """Restore persistent user data after replacement."""
    _copy_if_dir(os.path.join(backup_dir, "data"), os.path.join(PROJECT_ROOT, "data"))
    _copy_if_file(os.path.join(backup_dir, "config.toml"), os.path.join(PROJECT_ROOT, "config.toml"))
    _copy_if_file(os.path.join(backup_dir, "config.json"), os.path.join(PROJECT_ROOT, "config.json"))
    _copy_if_dir(os.path.join(backup_dir, "uploads"), os.path.join(PROJECT_ROOT, "uploads"))


def cleanup_temp_paths(zip_path: str, extract_dir: str) -> None:
    """Clean up temporary download/extract paths."""
    if zip_path and os.path.isfile(zip_path):
        with contextlib.suppress(OSError):
            os.remove(zip_path)
    if extract_dir and os.path.isdir(extract_dir):
        with contextlib.suppress(OSError):
            shutil.rmtree(extract_dir, ignore_errors=True)


def should_preserve(name: str) -> bool:
    """Check if a top-level entry should be preserved during replacement."""
    base = name.rstrip("/\\")
    return base in _PRESERVE or base.startswith("data_backup") or base == "_old_version"


def _copy_if_dir(src: str, dst: str) -> None:
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _copy_if_file(src: str, dst: str) -> None:
    if os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
