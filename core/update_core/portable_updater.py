"""Portable (ZIP distribution) self-update for Windows."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .portable_updater_support import (
    cleanup_temp_paths,
    create_backup,
    download_asset,
    extract_zip,
    read_version,
    replace_project_files,
    resolve_latest_download,
)

logger = logging.getLogger(__name__)

# Step names in execution order
STEPS = ("download", "backup", "extract", "replace", "complete")

def run_portable_update(
    emit_progress: Callable[[str, str, str], None],
    download_url: str | None = None,
) -> dict:
    """Execute a full portable ZIP update sequence.

    Args:
        emit_progress: callback(step, status, detail) to report progress.
            status is one of: "running", "success", "skipped", "error".
        download_url: optional direct URL to the ZIP asset. If None, the
            latest release is fetched from GitHub.

    Returns:
        dict with success, steps_completed, error, restart_required,
        old_version, new_version.
    """
    steps_completed: list[str] = []
    old_version = read_version()
    new_version = old_version
    zip_path = ""
    extract_dir = ""

    try:
        # ── Step 1: download ──
        emit_progress("download", "running", "Fetching release info...")
        expected_sha256 = None

        if not download_url:
            download_url, new_version, expected_sha256 = resolve_latest_download(old_version)
            if not download_url:
                error = "Portable ZIP asset not found in latest release"
                emit_progress("download", "error", error)
                return {
                    "success": False,
                    "steps_completed": steps_completed,
                    "error": error,
                    "restart_required": False,
                    "old_version": old_version,
                    "new_version": new_version,
                }

        emit_progress("download", "running", "Downloading ZIP...")
        zip_path = download_asset(
            download_url,
            old_version,
            emit_progress,
            expected_sha256=expected_sha256,
        )
        emit_progress("download", "success", "Download complete")
        steps_completed.append("download")

        # ── Step 2: backup ──
        emit_progress("backup", "running", "Backing up user data...")
        backup_dir = create_backup()
        emit_progress("backup", "success", f"Backup at {backup_dir}")
        steps_completed.append("backup")

        # ── Step 3: extract ──
        emit_progress("extract", "running", "Extracting ZIP...")
        extract_dir, source_dir = extract_zip(zip_path)
        emit_progress("extract", "success", "Extraction complete")
        steps_completed.append("extract")

        # ── Step 4: replace ──
        emit_progress("replace", "running", "Replacing application files...")
        replace_project_files(source_dir, backup_dir)
        new_version = read_version()

        emit_progress("replace", "success", "Files replaced successfully")
        steps_completed.append("replace")

        # ── Step 5: complete ──
        emit_progress("complete", "done",
                       f"Updated {old_version} -> {new_version}")
        steps_completed.append("complete")

        return {
            "success": True,
            "steps_completed": steps_completed,
            "error": None,
            "restart_required": True,
            "old_version": old_version,
            "new_version": new_version,
        }

    except Exception as exc:
        logger.error("Portable update failed: %s", exc, exc_info=True)
        emit_progress("error", "error", str(exc))
        return {
            "success": False,
            "steps_completed": steps_completed,
            "error": str(exc),
            "restart_required": False,
            "old_version": old_version,
            "new_version": new_version,
        }

    finally:
        cleanup_temp_paths(zip_path, extract_dir)
