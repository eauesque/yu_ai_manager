"""extensions/builtin_lan_cowork/core_impl/sync_manifest.py
Build and compare file manifests for WC/prompt sync.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

ManifestEntry = dict[str, object]  # {"hash": str, "mtime": float, "size": int}
Manifest = dict[str, ManifestEntry]  # relative_path -> entry

logger = logging.getLogger(__name__)


def file_hash(path: Path) -> str:
    """SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path) -> Manifest:
    """Scan a directory and build a manifest of files resolving within root."""
    manifest: Manifest = {}
    root = root.resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if not p.resolve().is_relative_to(root):
            logger.debug("Skipping sync manifest path outside root: %s", rel)
            continue
        stat = p.stat()
        manifest[rel] = {
            "hash": file_hash(p),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        }
    return manifest


def diff_manifests(local: Manifest, remote: Manifest) -> tuple[list[str], list[str]]:
    """Compare local and remote manifests.

    Returns (to_fetch, to_push):
    - to_fetch: files to download from remote (remote is newer or missing locally)
    - to_push: files to upload to remote (local is newer or missing remotely)
    """
    to_fetch: list[str] = []
    to_push: list[str] = []

    all_keys = set(local) | set(remote)
    for key in all_keys:
        l_entry = local.get(key)
        r_entry = remote.get(key)

        if l_entry is None and r_entry is not None:
            to_fetch.append(key)
        elif r_entry is None and l_entry is not None:
            to_push.append(key)
        elif l_entry["hash"] != r_entry["hash"]:
            # Different content — Last-Write-Wins by mtime
            if r_entry["mtime"] > l_entry["mtime"]:
                to_fetch.append(key)
            else:
                to_push.append(key)
        # Same hash → no action

    return to_fetch, to_push
