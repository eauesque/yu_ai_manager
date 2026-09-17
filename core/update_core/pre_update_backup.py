"""Create a pre-update backup of config and database files."""

from __future__ import annotations

import logging
import os
import shutil
import time

from core.update_core.detect import PROJECT_ROOT

logger = logging.getLogger(__name__)


def _read_version() -> str:
    """Read current version string for the backup directory name."""
    try:
        with open(os.path.join(PROJECT_ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip().replace(" ", "_")
    except OSError:
        return "unknown"


def create_pre_update_backup() -> dict:
    """Backup config.json and tags.db before an update.

    Returns:
        {"success": bool, "backup_path": str, "error": str | None}
    """
    try:
        version = _read_version()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(
            PROJECT_ROOT, "data", "backups",
            f"pre_update_{version}_{timestamp}",
        )
        os.makedirs(backup_dir, exist_ok=True)

        # Files to back up (relative to PROJECT_ROOT)
        targets = [
            os.path.join(PROJECT_ROOT, "config.toml"),
            os.path.join(PROJECT_ROOT, "config.json"),
            os.path.join(PROJECT_ROOT, "data", "tags.db"),
        ]

        copied = []
        for src in targets:
            if os.path.isfile(src):
                dst = os.path.join(backup_dir, os.path.basename(src))
                shutil.copy2(src, dst)
                copied.append(os.path.basename(src))
                logger.info("Backed up %s -> %s", src, dst)

        return {
            "success": True,
            "backup_path": backup_dir,
            "files": copied,
            "error": None,
        }

    except Exception as exc:
        logger.error("Pre-update backup failed: %s", exc)
        return {
            "success": False,
            "backup_path": "",
            "error": str(exc),
        }
