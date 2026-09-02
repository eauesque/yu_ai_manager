"""Support helpers for vectors.db connections and CLIP eligibility."""

import contextlib
import logging
import re
import threading

from core.services_core.db_cipher import apply_key, sqlite3
from core.services_core.db_state import get_vectors_db_path

logger = logging.getLogger(__name__)

_batch_vectors_local = threading.local()

_CLIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp",
    ".tiff", ".tif", ".heif", ".heic", ".jxl", ".svg",
    ".webm", ".mp4", ".avi", ".mov", ".mkv", ".m4v", ".ogv",
}
_CLIP_EXT_RE = r"\.(?:" + "|".join(ext.lstrip(".") for ext in sorted(_CLIP_EXTS)) + r")$"


def get_batch_vectors_con() -> sqlite3.Connection:
    """Dedicated long-timeout write connection to vectors.db for batch indexing."""
    con = getattr(_batch_vectors_local, "con", None)
    if con is not None:
        try:
            con.execute("SELECT 1")
            return con
        except Exception:
            logger.debug("pooled connection failed its liveness probe", exc_info=True)
    con = sqlite3.connect(str(get_vectors_db_path()), timeout=60.0)
    apply_key(con)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("PRAGMA synchronous=NORMAL")
    _batch_vectors_local.con = con
    return con


def close_batch_vectors_con() -> None:
    """Close the batch write connection for the current thread (call on thread exit)."""
    con = getattr(_batch_vectors_local, "con", None)
    if con is not None:
        with contextlib.suppress(Exception):
            con.close()
        _batch_vectors_local.con = None


def refresh_clip_eligible(con=None) -> None:
    """Rebuild the persistent CLIP-eligible helper table."""
    if con is None:
        from core.services_core.clip_search_helper_service import (
            refresh_clip_eligible_files_table,
        )

        refresh_clip_eligible_files_table()
        return
    rebuild_clip_eligible_files(con)


def ensure_clip_eligible_table(con) -> None:
    """Compatibility shim until vector_store read paths switch to helper table."""
    ensure_clip_eligible_files_table(con)


def ensure_clip_eligible_files_table(con) -> None:
    """Ensure the persistent helper table exists."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS clip_eligible_files (
            file_id INTEGER PRIMARY KEY,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """
    )


def rebuild_clip_eligible_files(con) -> int:
    """Fully rebuild the persistent helper table and return the row count."""
    ensure_clip_eligible_files_table(con)
    _ensure_regexp_function(con)
    con.execute("DELETE FROM clip_eligible_files")
    con.execute(
        "INSERT INTO clip_eligible_files (file_id)"
        " SELECT id FROM files"
        " WHERE is_deleted = 0"
        "   AND lower(path) REGEXP ?"
        "   AND path NOT LIKE '%.7z!%'",
        (_CLIP_EXT_RE,),
    )
    con.commit()
    row = con.execute("SELECT COUNT(*) FROM clip_eligible_files").fetchone()
    return row[0] if row else 0


def _ensure_regexp_function(con) -> None:
    """Register REGEXP for raw sqlite connections used in tests or helper rebuilds."""
    with contextlib.suppress(Exception):
        con.create_function(
            "REGEXP",
            2,
            lambda pattern, value: 1 if value is not None and re.search(pattern, value) else 0,
        )
