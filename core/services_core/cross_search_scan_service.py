"""Cross-search scan orchestration service."""

from __future__ import annotations

import contextlib
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from core.services_core.db_state import get_db

if TYPE_CHECKING:
    from core.jobs_core.jobs_model import Job

logger = logging.getLogger(__name__)

_EXCLUDED_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".eggs",
    "dist", "build", ".next", ".nuxt",
})

_MAX_FILE_SIZE = {
    ".pdf": 50 * 1024 * 1024,
}
_DEFAULT_MAX_SIZE = 5 * 1024 * 1024


def scan_text_files(
    scan_roots: list[str],
    job: Job | None = None,
) -> dict:
    """Scan supported document files under scan_roots and register them in DB."""
    from extensions.builtin_cross_search.core_impl import store
    from extensions.builtin_cross_search.core_impl.extractors import (
        extract_text,
    )

    con = get_db()
    store.ensure_tables(con)

    if job:
        job.update(phase="collecting", message="ファイルを収集中...")

    existing_by_path = _get_existing_index(con, getattr(store, "get_active_file_index", None))

    if job:
        job.progress(0, 0, "")
        job.update(phase="indexing", message="ファイルを処理中...")

    stats = {"found": 0, "new": 0, "updated": 0, "skipped": 0, "deleted": 0, "errors": 0}
    found_paths: set[str] | None = None
    use_seen_table = _prepare_seen_table(store, con)
    seen_path_batch: list[str] = []
    if not use_seen_table:
        found_paths = set()
    last_progress_at = 0.0

    for i, fpath in enumerate(_iter_files(scan_roots), start=1):
        if job and job.cancelled:
            _rollback(con)
            job.complete_cancelled()
            return stats

        path_str = str(fpath)
        stats["found"] = i
        if found_paths is not None:
            found_paths.add(path_str)
        if use_seen_table:
            seen_path_batch.append(path_str)
            if len(seen_path_batch) >= 500:
                _flush_seen_paths(store, con, seen_path_batch)

        try:
            st = fpath.stat()
            file_mtime = st.st_mtime
            file_size = st.st_size

            max_size = _MAX_FILE_SIZE.get(fpath.suffix.lower(), _DEFAULT_MAX_SIZE)
            if file_size > max_size:
                stats["skipped"] += 1
                _maybe_progress(job, i, fpath.name, last_progress_at)
                last_progress_at = time.monotonic()
                continue

            existing = existing_by_path.get(path_str)
            if existing is None and not existing_by_path:
                existing = store.get_text_file_by_path(con, path_str)
            if existing and abs(existing["mtime"] - file_mtime) < 0.01:
                stats["skipped"] += 1
                _maybe_progress(job, i, fpath.name, last_progress_at)
                last_progress_at = time.monotonic()
                continue

            result = extract_text(fpath)
            if result is None:
                stats["skipped"] += 1
                _maybe_progress(job, i, fpath.name, last_progress_at)
                last_progress_at = time.monotonic()
                continue

            title, content = result
            if not content.strip():
                stats["skipped"] += 1
                _maybe_progress(job, i, fpath.name, last_progress_at)
                last_progress_at = time.monotonic()
                continue

            _upsert_text_file(
                store,
                con,
                path_str,
                file_mtime,
                file_size,
                title,
                content,
            )

            if existing:
                stats["updated"] += 1
            else:
                stats["new"] += 1

        except Exception as exc:
            logger.warning("Scan error: %s: %s", fpath, exc)
            stats["errors"] += 1

        _maybe_progress(job, i, fpath.name, last_progress_at)
        last_progress_at = time.monotonic()

    if use_seen_table:
        _flush_seen_paths(store, con, seen_path_batch)
        deleted = store.mark_missing_deleted_by_seen_table(con, commit=False)
    else:
        try:
            deleted = store.mark_missing_deleted(con, found_paths or set(), commit=False)
        except TypeError:
            deleted = store.mark_missing_deleted(con, found_paths or set())
    _commit(con)
    stats["deleted"] = deleted

    if job:
        msg = (
            f"Done: {stats['new']} added, {stats['updated']} updated, "
            f"{stats['skipped']} skipped"
        )
        if deleted:
            msg += f", {deleted} deleted"
        if stats["errors"]:
            msg += f", {stats['errors']} 件エラー"
        job.complete(msg)

    return stats


def _collect_files(scan_roots: list[str]) -> list[Path]:
    """Collect supported file paths under scan_roots."""
    return sorted(_iter_files(scan_roots))


def _iter_files(scan_roots: list[str]) -> Iterator[Path]:
    """Yield supported file paths under scan_roots without materializing them."""
    try:
        from extensions.builtin_cross_search.core_impl.extractors import (
            SUPPORTED_EXTENSIONS,
        )
    except ImportError:
        SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}

    seen: set[str] = set()

    for root in scan_roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [
                d for d in dirnames
                if d not in _EXCLUDED_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                full = Path(dirpath) / fname
                resolved = str(full.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    yield full


def _get_existing_index(con, get_active_file_index):
    if not callable(get_active_file_index):
        return {}
    try:
        return get_active_file_index(con)
    except Exception as exc:
        logger.debug("Failed to load cross-search file index: %s", exc)
        return {}


def _maybe_progress(job: Job | None, current: int, detail: str, last_progress_at: float) -> None:
    if not job:
        return
    now = time.monotonic()
    if current == 1 or current % 50 == 0 or (now - last_progress_at) >= 0.5:
        job.progress(current, 0, detail)


def _prepare_seen_table(store, con) -> bool:
    ensure_seen_temp_table = getattr(store, "ensure_seen_temp_table", None)
    add_seen_paths = getattr(store, "add_seen_paths", None)
    mark_missing = getattr(store, "mark_missing_deleted_by_seen_table", None)
    if not (callable(ensure_seen_temp_table) and callable(add_seen_paths) and callable(mark_missing)):
        return False
    try:
        ensure_seen_temp_table(con)
    except Exception as exc:
        logger.debug("Failed to prepare cross-search seen table: %s", exc)
        return False
    return True


def _flush_seen_paths(store, con, paths: list[str]) -> None:
    if not paths:
        return
    store.add_seen_paths(con, paths)
    paths.clear()


def _upsert_text_file(store, con, path: str, mtime: float, size: int, title: str, content: str) -> None:
    try:
        store.upsert_text_file(
            con,
            path,
            mtime,
            size,
            title,
            content,
            commit=False,
        )
    except TypeError:
        store.upsert_text_file(con, path, mtime, size, title, content)


def _commit(con) -> None:
    with contextlib.suppress(Exception):
        con.commit()


def _rollback(con) -> None:
    with contextlib.suppress(Exception):
        con.rollback()
