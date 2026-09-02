"""Post-scan housekeeping helpers."""

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

import contextlib

from core.cleanup_core.cleanup import cleanup_normalize_tags
from core.configuration.api import load_config_json, save_config_json
from core.services_core.db_api import get_db, get_raw_db, get_readonly_db
from core.services_core.db_write import submit_db_write, submit_db_write_no_wait

# SQLite SQLITE_MAX_VARIABLE_NUMBER default is 999; chunk to stay safe
_CHUNK_SIZE = 500


def _chunked_in_execute(
    con: sqlite3.Connection,
    sql_before_in: str,
    sql_after_in: str,
    ids: list,
    extra_params: tuple = (),
) -> None:
    """Safely execute SQL with IN clause by chunking."""
    for i in range(0, len(ids), _CHUNK_SIZE):
        chunk = ids[i: i + _CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        sql = f"{sql_before_in} IN ({placeholders}){sql_after_in}"
        con.execute(sql, list(chunk) + list(extra_params))


def sync_deleted_files(root_path: str) -> tuple[int, list[int]]:
    try:
        con_ro = get_readonly_db()
        root_norm = root_path.replace("\\\\", "/")
        like_pattern = root_norm + "%"
        like_pattern2 = root_path.replace("/", "\\\\") + "%"
        db_files = con_ro.execute(
            "SELECT id, path FROM files WHERE (path LIKE ? OR path LIKE ?) AND is_deleted=0",
            (like_pattern, like_pattern2),
        )

        from core.helpers_core.helpers_text_path import archive_part as _ap

        delete_ids = []
        for row in db_files:
            file_path = row["path"]
            check_path = _ap(file_path) if "!" in file_path else file_path
            if not os.path.exists(check_path):
                delete_ids.append(row["id"])

        if not delete_ids:
            return 0, []

        def _write() -> int:
            con_cleanup = get_db()
            _chunked_in_execute(con_cleanup, "DELETE FROM file_tags WHERE file_id", "", delete_ids)
            _chunked_in_execute(con_cleanup, "DELETE FROM templates WHERE file_id", "", delete_ids)
            _chunked_in_execute(con_cleanup, "DELETE FROM files WHERE id", "", delete_ids)
            con_cleanup.commit()
            return len(delete_ids)

        deleted_count = submit_db_write(_write)
        logger.info(f"[Scan] Removed {deleted_count} missing files from DB")
        return deleted_count, delete_ids
    except Exception as e:
        logger.info(f"[Scan] Missing file cleanup skipped: {e}")
        return 0, []


def normalize_tags_after_scan() -> int:
    try:
        def _write() -> int:
            con = get_db()
            normalized_count = cleanup_normalize_tags(con, dry_run=False)
            con.commit()
            return normalized_count

        normalized_count = submit_db_write(_write)
        if normalized_count > 0:
            logger.info(f"[Scan] Auto-normalized {normalized_count} tags")
        return normalized_count
    except Exception as e:
        logger.info(f"[Scan] Tag normalization skipped: {e}")
        return 0


def optimize_fts_tables() -> None:
    """Rebuild and optimize FTS5 tables.

    Called after scan completion.
    - files_path_fts: As a content-sync table, rebuild reconstructs the inverted
      index from the content table (prevents zero-result search bugs due to missing tokens).
    - Others: Only perform segment merging via optimize.
    """
    try:
        def _write() -> None:
                try:
                    con = get_raw_db()
                    with contextlib.suppress(Exception):
                        con.execute(
                            "INSERT INTO files_path_fts(files_path_fts) VALUES('rebuild')"
                        )
                    for fts_table in ["templates_fts", "md_files_fts", "chat_messages_fts", "files_path_fts"]:
                        with contextlib.suppress(Exception):
                            con.execute(
                                f"INSERT INTO {fts_table}({fts_table}) VALUES('optimize')"
                            )
                    con.commit()
                except Exception:
                    # Best-effort maintenance; never fail caller -- but FTS
                    # optimisation that has quietly stopped running looks the
                    # same as one that has nothing to do.
                    logger.debug("FTS maintenance did not complete", exc_info=True)

        submit_db_write_no_wait(_write)
        logger.info("[Scan] FTS5 rebuild + optimize enqueued")
    except Exception as e:
        logger.info(f"[Scan] FTS5 optimize skipped: {e}")


def wal_checkpoint() -> None:
    """Execute a WAL checkpoint to keep the WAL file size small.

    Called after scan completion to merge accumulated WAL pages into the main DB.
    Uses PASSIVE mode so it does not block active readers.
    """
    try:
        def _write() -> None:
            try:
                con = get_raw_db()
                con.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                logger.debug("scan step failed", exc_info=True)

        submit_db_write_no_wait(_write)
        logger.info("[Scan] WAL checkpoint enqueued")
    except Exception as e:
        logger.info(f"[Scan] WAL checkpoint skipped: {e}")


def purge_orphan_files() -> int:
    """Remove DB entries not under any registered scan root.

    After roots are removed from config.json, old file entries remain
    in the database.  This function detects and deletes those orphans.
    """
    purged = 0
    try:
        from core.helpers_core.helpers_text_path import archive_part as _ap
        from core.platform import resolve_real_path

        config = load_config_json(None)
        roots = config.get("scan_roots", [])
        # Build list of resolved root paths (all enabled + disabled)
        resolved_roots = []
        for r in roots:
            p = r.get("path", "") if isinstance(r, dict) else ""
            if p:
                resolved_roots.append(resolve_real_path(p))

        if not resolved_roots:
            return 0

        con_ro = get_readonly_db()
        all_files = con_ro.execute(
            "SELECT id, path FROM files WHERE is_deleted=0"
        )

        orphan_ids = []
        for row in all_files:
            fpath = resolve_real_path(_ap(row["path"]) if "!" in row["path"] else row["path"])
            under_root = False
            for root in resolved_roots:
                if fpath.startswith(root + os.sep) or fpath == root:
                    under_root = True
                    break
            if not under_root:
                orphan_ids.append(row["id"])

        if orphan_ids:
            def _write() -> None:
                con = get_db()
                _chunked_in_execute(con, "DELETE FROM file_tags WHERE file_id", "", orphan_ids)
                _chunked_in_execute(con, "DELETE FROM templates WHERE file_id", "", orphan_ids)
                _chunked_in_execute(con, "DELETE FROM files WHERE id", "", orphan_ids)
                con.commit()

            submit_db_write(_write)
            purged = len(orphan_ids)
            logger.info(f"[Scan] Purged {purged} orphan files not under any registered root")
    except Exception as e:
        logger.info(f"[Scan] Orphan purge skipped: {e}")
    return purged


def auto_register_scan_root(root_path: str, recursive: bool) -> None:
    try:
        from core.platform import resolve_real_path

        config = load_config_json(None)
        if "scan_roots" not in config:
            config["scan_roots"] = []
        existing_paths = {
            resolve_real_path(r.get("path", ""))
            for r in config["scan_roots"]
        }
        norm_root = resolve_real_path(root_path)
        if norm_root not in existing_paths:
            config["scan_roots"].append(
                {
                    "path": root_path,
                    "enabled": True,
                    "recursive": recursive,
                    "comment": "",
                }
            )
            save_config_json(config)
            logger.info(f"[Scan] Auto-registered scan root: {root_path}")
    except Exception as e:
        logger.info(f"[Scan] Auto-register root failed: {e}")
