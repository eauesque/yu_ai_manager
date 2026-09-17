"""Read helpers for WD-Tagger orchestration."""

from __future__ import annotations


def get_active_file_record(file_id: int):
    """Fetch an active file row for WD-Tagger workflows."""
    from core.services_core.db_state import get_readonly_db

    return get_readonly_db().execute(
        "SELECT id, path, meta_source FROM files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()


def get_active_file_paths(file_ids: list[int]) -> dict[int, str]:
    """Fetch active file paths for the given IDs.

    Chunks the ID list to stay under SQLite's SQLITE_MAX_VARIABLE_NUMBER
    (default 999 on older builds, 32766 on newer). The full-corpus
    WD-Tagger batch can pass 300k+ IDs at once, which would otherwise
    raise ``sqlite3.OperationalError: too many SQL variables``.
    """
    from core.services_core.db_state import get_readonly_db

    if not file_ids:
        return {}

    # Conservative chunk size that works on every SQLite build we ship
    # (older Windows wheels still cap at 999). The 500-row roundtrips
    # are cheap relative to the inference work that follows.
    CHUNK = 500
    con = get_readonly_db()
    out: dict[int, str] = {}
    for start in range(0, len(file_ids), CHUNK):
        chunk = file_ids[start:start + CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f"SELECT id, path FROM files "
            f"WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        for row in rows:
            out[row["id"]] = row["path"]
    return out
