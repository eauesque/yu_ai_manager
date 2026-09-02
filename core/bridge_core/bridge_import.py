"""Auto-import saved bridge images into the application database."""

from __future__ import annotations

import logging
from pathlib import Path

from core.services_core.db_state import get_config, get_db_path, get_raw_db

logger = logging.getLogger(__name__)


def import_saved_files(saved_paths: list[str]) -> tuple[int, dict[str, int | None]]:
    """Register saved image files in the database via scan_one_regular.

    Returns ``(imported_count, path_to_file_id)`` where ``path_to_file_id``
    maps every input path to its DB ``file_id`` on success, or ``None`` if
    the file was missing, failed to import, or the DB was unavailable.
    Uses SAVEPOINT per file so a failure doesn't leave partial state
    (e.g. file row + tags committed but template missing).

    On completion (even with zero imports), emits ``SCAN_COMPLETE`` with the
    ids of added/updated files so the UI sidebar / folder tree refreshes the
    same way it does after a periodic scan. Without this, files imported via
    auto-import only appeared in the index after the next periodic scan.
    """
    # Pre-populate mapping with None so callers always see a key for every
    # input path, even on early-return / DB-unavailable code paths.
    path_to_id: dict[str, int | None] = {p: None for p in saved_paths}

    if not saved_paths:
        return 0, path_to_id

    from core.scan_core.scanner_regular import scan_one_regular

    try:
        db_path = get_db_path()
    except RuntimeError as exc:
        logger.warning("auto_import: DB path unavailable (%s), skipping (paths=%d)", exc, len(saved_paths))
        return 0, path_to_id
    if not db_path:
        logger.warning("auto_import: DB path not configured, skipping (paths=%d)", len(saved_paths))
        return 0, path_to_id

    config = get_config()
    imported = 0
    added_ids: list[int] = []
    updated_ids: list[int] = []
    skipped_missing = 0
    failed = 0
    try:
        con = get_raw_db()
        for path_str in saved_paths:
            p = Path(path_str)
            if not p.exists():
                skipped_missing += 1
                continue
            try:
                con.execute("SAVEPOINT auto_import_file")
                result = scan_one_regular(
                    con, p, config, force=True, compute_hash=False,
                )
                con.execute("RELEASE SAVEPOINT auto_import_file")
                con.commit()
                if result is not None:
                    imported += 1
                    action, file_id = result
                    fid_int = int(file_id)
                    path_to_id[path_str] = fid_int
                    if action == "added":
                        added_ids.append(fid_int)
                    else:
                        updated_ids.append(fid_int)
            except Exception as exc:
                failed += 1
                logger.warning(
                    "auto_import: failed to import %s: %s",
                    path_str, exc, exc_info=True,
                )
                try:
                    con.execute("ROLLBACK TO SAVEPOINT auto_import_file")
                    con.execute("RELEASE SAVEPOINT auto_import_file")
                    con.commit()
                except Exception:
                    logger.warning("step failed", exc_info=True)
    except Exception as exc:
        logger.error("auto_import: DB connection failed: %s", exc, exc_info=True)
        return imported, path_to_id

    # Always log so silent failures (imported=0, all warnings) are visible.
    logger.info(
        "auto_import: registered %d/%d files (added=%d updated=%d failed=%d missing=%d)",
        imported, len(saved_paths), len(added_ids), len(updated_ids), failed, skipped_missing,
    )

    # Notify UI so the sidebar / folder tree refreshes immediately. Without
    # this event, newly imported files only show up after the next periodic
    # scan (or a manual page reload after the import completes), which made
    # bridge sweep batch save look like "auto_import not working".
    if added_ids or updated_ids:
        try:
            from core.event_bus import emit
            from core.event_bus.event_types import SCAN_COMPLETE
            emit(
                SCAN_COMPLETE,
                {
                    # `count` is what scan_history._on_scan_complete reads;
                    # without it the history entry would always show 0.
                    "count": imported,
                    "files": imported,
                    "added": len(added_ids),
                    "updated": len(updated_ids),
                    "errors": failed,
                    "deleted": 0,
                    "elapsed_seconds": 0,
                    "job_id": "auto_import",
                    "added_count": len(added_ids),
                    "updated_count": len(updated_ids),
                    "added_ids": added_ids,
                    "updated_ids": updated_ids,
                    "source": "auto_import",
                },
                source="auto_import",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("auto_import: SCAN_COMPLETE emit failed: %s", exc)

        # Drop the in-memory search cache so the next /api/search falls back
        # to SQL and returns the newly added files immediately.  Without this,
        # ensure_built() serves stale records while the background rebuild
        # runs (~30 s on large databases), making Bridge-generated images
        # invisible until the rebuild completes.
        try:
            from core.search_api.file_meta_cache import file_meta_cache
            file_meta_cache.reset_cold()
        except Exception as exc:  # noqa: BLE001
            logger.debug("auto_import: file_meta_cache reset_cold failed: %s", exc)

    return imported, path_to_id


def import_saved_files_async(saved_paths: list[str]) -> None:
    """Enqueue import_saved_files on the dedicated DB-writer thread.

    Returns immediately. The write is serialised through the existing
    single-writer executor (db_write._db_writer_executor), so concurrent
    bridge completions no longer compete for the SQLite write lock.
    """
    if not saved_paths:
        return
    from core.services_core.db_write import submit_db_write_no_wait

    def _wrap(paths: list[str]) -> None:
        # Discard the (count, mapping) tuple for fire-and-forget callers.
        import_saved_files(paths)

    submit_db_write_no_wait(_wrap, saved_paths)


def import_saved_files_sync(saved_paths: list[str]) -> dict[str, int | None]:
    """Synchronously import saved files via the dedicated DB writer thread.

    Blocks until indexing completes and returns a path->file_id mapping
    (None for missing / unindexable files).

    Use this when the caller needs the file_id back (e.g. Sweep flows that
    embed file_id in the response so the client can deep-link to /sweep/<id>).
    For non-Sweep generates, prefer import_saved_files_async to avoid
    blocking on the writer queue.
    """
    if not saved_paths:
        return {}
    from core.services_core.db_write import submit_db_write
    _count, mapping = submit_db_write(import_saved_files, saved_paths)
    return mapping
