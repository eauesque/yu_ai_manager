"""Preparation stage for background scan runtime."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from core.configuration.api import load_config
from core.scan.runtime_fs import enumerate_with_retry, probe_filesystem
from core.scan_core.archive_listing_cache import ArchiveListingCache
from core.scan_core.scanner import iter_files_with_zips
from core.schema_core.schema import init_db, migrate_db
from core.services_core.db_api import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write, submit_db_write_no_wait

SCAN_EXTS = [
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".jxl", ".avif", ".heif", ".heic", ".svg",
    ".webm", ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".ogv",
    ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac",
    ".pdf",
]

# 500 stays well below SQLite's SQLITE_MAX_VARIABLE_NUMBER (999 default / 32766
# with modern builds) and maps cleanly onto the composite index
# idx_files_deleted_path ON files(is_deleted, path).  Each chunk is an indexed
# lookup; even 200k-file libraries produce ~400 fast in-process round-trips.
_IN_CHUNK_SIZE = 500


def init_scan_context(root_path: str):
    config = load_config(None)
    enable_fts = bool(config.get("enable_fts", True))

    def _init_schema() -> None:
        con = get_db()
        init_db(con, enable_fts=enable_fts)
        migrate_db(con)
        con.commit()

    submit_db_write(_init_schema)

    root = Path(root_path)
    is_remote = str(root).startswith("\\\\") or str(root).startswith("//")
    rfs = config.get("remote_fs", {})

    return {
        "config": config,
        "root": root,
        "is_remote": is_remote,
        "rfs": rfs,
    }


def ensure_remote_access(root, root_path: str, rfs: dict, job) -> bool:
    stop_event = getattr(job, "stop_event", None) if job else None
    if not probe_filesystem(
        root,
        retries=rfs.get("probe_retries", 6),
        wait=rfs.get("probe_wait", 5.0),
        stop_event=stop_event,
    ):
        debug_info = [f"path_repr={repr(root_path)}"]
        try:
            debug_info.append(f"os.exists={os.path.exists(root_path)}")
        except Exception as e:
            debug_info.append(f"os.exists=ERR({e})")
        try:
            debug_info.append(f"os.isdir={os.path.isdir(root_path)}")
        except Exception as e:
            debug_info.append(f"os.isdir=ERR({e})")
        try:
            debug_info.append(f"Path.exists={root.exists()}")
        except Exception as e:
            debug_info.append(f"Path.exists=ERR({e})")
        try:
            debug_info.append(f"len(str(root))={len(str(root))}")
        except Exception as exc:
            logger.debug("Debug info collection failed: %s", exc)

        job.fail(
            f"ファイルシステムにアクセスできません: {root_path}\n"
            f"デバッグ: {', '.join(debug_info)}\n"
            "WSL/NASがスリープ中の可能性があります。\n"
            "エクスプローラーでフォルダを一度開いてから再試行してください。"
        )
        return False
    return True


def filter_already_scanned(all_files, root_path: str) -> list:
    """For resume: filter out paths already registered in the DB, returning only unscanned files.

    Checks enumerated paths against the DB in chunks and excludes registered files.
    Files whose mtime/size changed are re-scan evaluated inside scan_one,
    so here we only filter quickly based on whether the path exists in the DB.
    """
    from core.platform.path_normalize import normalize_path

    if not all_files:
        return all_files

    keyed_files = [
        (f, f if isinstance(f, str) else normalize_path(f))
        for f in all_files
    ]
    read_con = get_readonly_db()
    existing_paths: set[str] = set()
    for start in range(0, len(keyed_files), _IN_CHUNK_SIZE):
        keys = [key for _, key in keyed_files[start:start + _IN_CHUNK_SIZE]]
        placeholders = ",".join("?" for _ in keys)
        rows = read_con.execute(
            f"SELECT path FROM files WHERE is_deleted=0 AND path IN ({placeholders})",
            keys,
        ).fetchall()
        existing_paths.update(row[0] for row in rows)

    if not existing_paths:
        return all_files

    return [f for f, key in keyed_files if key not in existing_paths]


def collect_scan_targets(root, recursive: bool, scan_zips: bool, is_remote: bool, rfs: dict, job, exclude_dirs=()):
    """Collect scan target files.  Returns (file_list, error_list).

    Enumeration errors are persisted via the serialized DB writer and also
    returned so the caller can include them in the scan summary.
    """
    stop_event = getattr(job, "stop_event", None) if job else None
    enum_errors: list = []

    def _on_archive(path: str) -> None:
        """Report which archive is being enumerated during counting."""
        if job is not None:
            try:
                name = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            except Exception:
                name = path
            job.update(message=f"ZIP/7z listing: {name}")

    def _on_error(path: str, error_type: str, detail: str) -> None:
        """Record enumeration errors for post-scan review."""
        enum_errors.append({"path": path, "error_type": error_type, "detail": detail})
        logger.warning(f"Enumeration error ({error_type}): {path}: {detail}")
        try:
            submit_db_write_no_wait(
                lambda: _record_scan_error(path, error_type, detail)
            )
        except Exception as exc:
            logger.debug("Failed to record enumeration error: %s", exc)

    archive_cache = ArchiveListingCache() if scan_zips else None

    if is_remote:
        files = enumerate_with_retry(
            root,
            recursive,
            SCAN_EXTS,
            scan_zips,
            max_retries=rfs.get("enumerate_retries", 4),
            wait=rfs.get("enumerate_wait", 5.0),
            job=job,
            exclude_dirs=exclude_dirs,
            archive_cache=archive_cache,
        )
        if archive_cache is not None:
            archive_cache.save()
        return files, enum_errors, archive_cache

    files = list(iter_files_with_zips(
        root, recursive, SCAN_EXTS,
        scan_zips=scan_zips, exclude_dirs=exclude_dirs,
        stop_event=stop_event,
        on_archive=_on_archive if scan_zips else None,
        on_error=_on_error,
        archive_cache=archive_cache,
    ))
    if archive_cache is not None:
        archive_cache.save()
    return files, enum_errors, archive_cache


def _record_scan_error(path: str, error_type: str, detail: str) -> None:
    from core.scan_core.scan_errors import record_scan_error

    con = get_db()
    record_scan_error(con, path, error_type, detail)
    con.commit()
