"""Write helpers for auto-scan watcher batch processing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from core.platform import normalize_path
from core.services_core.db_state import get_db

logger = logging.getLogger(__name__)

_ARCHIVE_EXTS = {".zip", ".7z"}


def process_watcher_batch(
    batch: dict[str, tuple],
    config: dict,
    watched_roots: list[str],
    is_under_watched_root: Callable[[str], bool],
) -> tuple[int, int, int, int]:
    """Process watcher file-system events and return counters."""
    from core.models_core.models_files import mark_deleted
    from core.scan_core.scanner_regular import scan_one_regular

    con = get_db()
    added = modified = deleted = errors = 0

    archive_batch: dict[str, tuple] = {}
    regular_batch: dict[str, tuple] = {}
    for path, val in batch.items():
        ext = Path(path).suffix.lower()
        if ext in _ARCHIVE_EXTS:
            archive_batch[path] = val
        else:
            regular_batch[path] = val

    if archive_batch:
        logger.info(
            "Watcher: %d archive(s) in batch: %s",
            len(archive_batch),
            list(archive_batch.keys()),
        )

    for path, (action, _ts) in regular_batch.items():
        try:
            if not is_under_watched_root(path):
                logger.warning(
                    "Watcher: SKIPPED out-of-scope file: %s "
                    "(not under any watched root: %s)",
                    path,
                    watched_roots,
                )
                continue
            if action == "deleted":
                norm = normalize_path(Path(path))
                mark_deleted(con, norm)
                deleted += 1
            else:
                p = Path(path)
                if p.exists():
                    scan_one_regular(
                        con,
                        p,
                        config,
                        force=False,
                        compute_hash=bool(config.get("compute_hash", False)),
                    )
                    if action == "created":
                        added += 1
                    else:
                        modified += 1
        except Exception:
            logger.debug("Watcher: error processing %s", path, exc_info=True)
            errors += 1

    archive_module = import_module("watcher_archive")
    a, m, d, e = archive_module.flush_archives(con, archive_batch, config)
    added += a
    modified += m
    deleted += d
    errors += e
    if added or modified or deleted:
        con.commit()

    return added, modified, deleted, errors
