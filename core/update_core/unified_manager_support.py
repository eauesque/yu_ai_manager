"""Support helpers for unified update management."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from core.update_core.detect import PROJECT_ROOT

logger = logging.getLogger(__name__)


def git_remote_head(ext_dir: Path, timeout: int = 30) -> str | None:
    """Fetch and return the remote HEAD commit hash for a git repo."""
    try:
        subprocess.run(
            ["git", "fetch", "--quiet"],
            cwd=str(ext_dir),
            capture_output=True,
            timeout=timeout,
        )
        result = subprocess.run(
            ["git", "rev-parse", "FETCH_HEAD"],
            cwd=str(ext_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def git_local_head(ext_dir: Path) -> str | None:
    """Return the local HEAD commit hash for a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ext_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def git_commit_count_behind(ext_dir: Path) -> int:
    """Return how many commits local HEAD is behind remote."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..FETCH_HEAD"],
            cwd=str(ext_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass
    return 0


def backup_extension_configs() -> dict:
    """Backup extension configuration before updates."""
    config_path = os.path.join(PROJECT_ROOT, "data", "extension_config.json")
    if not os.path.isfile(config_path):
        return {"success": True, "backup_path": "", "error": None, "skipped": True}

    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(PROJECT_ROOT, "data", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"extension_config_{timestamp}.json")
        shutil.copy2(config_path, backup_path)
        logger.info("Extension config backed up to %s", backup_path)
        return {"success": True, "backup_path": backup_path, "error": None}
    except Exception as exc:
        logger.error("Extension config backup failed: %s", exc)
        return {"success": False, "backup_path": "", "error": str(exc)}
