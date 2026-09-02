"""Filesystem probe/enumeration helpers for scan runtime."""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from core.scan_core.scanner import iter_files_with_zips


def probe_filesystem(root: Path, retries: int = 6, wait: float = 5.0, stop_event=None) -> bool:
    """Probe remote filesystem readiness (WSL/NAS/SMB wake-up)."""
    root_str = str(root)
    for attempt in range(retries):
        if stop_event is not None and stop_event.is_set():
            logger.info(f"Filesystem probe cancelled at attempt {attempt + 1}")
            return False
        try:
            if os.path.exists(root_str) and os.path.isdir(root_str):
                logger.info(f"Filesystem probe OK on attempt {attempt + 1}: {root_str}")
                return True
            logger.info(
                f"Probe attempt {attempt + 1}/{retries}: "
                f"exists={os.path.exists(root_str)}, isdir={os.path.isdir(root_str)}"
            )
        except (PermissionError, OSError) as e:
            logger.info(f"Probe attempt {attempt + 1}/{retries}: {e}")

        if attempt < retries - 1:
            actual_wait = wait * (1.5 ** attempt)
            logger.info(f"Retrying in {actual_wait:.0f}s...")
            # Use stop_event.wait() for interruptible sleep
            if stop_event is not None:
                if stop_event.wait(timeout=actual_wait):
                    logger.info("Filesystem probe cancelled during wait")
                    return False
            else:
                time.sleep(actual_wait)

    logger.warning(f"Filesystem probe failed after {retries} attempts: {root_str}")
    return False


def enumerate_with_retry(
    root: Path,
    recursive: bool,
    exts: list,
    scan_zips: bool,
    max_retries: int = 5,
    wait: float = 10.0,
    job=None,
    exclude_dirs=(),
    archive_cache=None,
) -> list:
    """Enumerate files with retry to handle remote FS wake-up lag."""
    stop_event = getattr(job, "stop_event", None) if job else None
    for attempt in range(max_retries):
        if stop_event is not None and stop_event.is_set():
            return []
        try:
            all_files = list(iter_files_with_zips(
                root, recursive, exts,
                scan_zips=scan_zips, exclude_dirs=exclude_dirs,
                stop_event=stop_event,
                archive_cache=archive_cache,
            ))
        except (PermissionError, OSError) as e:
            logger.warning(f"File enumeration attempt {attempt + 1} failed: {e}")
            all_files = []

        if len(all_files) > 0:
            return all_files

        if attempt < max_retries - 1:
            retry_wait = wait * (attempt + 1)
            msg = f"ファイルが見つかりません（試行 {attempt + 1}/{max_retries}）、{retry_wait:.0f}秒後にリトライ..."
            logger.info(msg)
            if job:
                job.update(phase="connecting", message=msg)
            # Use stop_event.wait() for interruptible sleep
            if stop_event is not None:
                if stop_event.wait(timeout=retry_wait):
                    return []
            else:
                time.sleep(retry_wait)

    return []
