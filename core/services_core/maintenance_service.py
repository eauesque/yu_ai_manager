"""Synchronous database maintenance helpers for Quart routes."""

from __future__ import annotations

from core.services_core.app_runtime_state import get_db_path


def get_db_stats() -> dict:
    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    page_count = con.execute("PRAGMA page_count").fetchone()[0]
    freelist_count = con.execute("PRAGMA freelist_count").fetchone()[0]
    # SQLCipher returns TEXT for this pragma via its page_size hook.
    page_size = int(con.execute("PRAGMA page_size").fetchone()[0])
    free_ratio = round(freelist_count / page_count, 4) if page_count else 0
    db_path = get_db_path()
    size_mb = round(db_path.stat().st_size / (1024 * 1024), 2) if db_path.exists() else 0
    return {
        "page_count": page_count,
        "freelist_count": freelist_count,
        "page_size": page_size,
        "free_ratio": free_ratio,
        "size_mb": size_mb,
    }


def get_scan_error_stats() -> list[dict]:
    from core.services_core.db_state import get_readonly_db

    rows = get_readonly_db().execute(
        "SELECT error_type, COUNT(*) as c FROM scan_errors WHERE resolved=0 "
        "GROUP BY error_type ORDER BY c DESC LIMIT 10"
    )
    return [{"error_type": row[0], "count": row[1]} for row in rows]


def vacuum_database() -> dict:
    from core.services_core.db_state import get_db

    db_path = get_db_path()
    size_before = db_path.stat().st_size if db_path.exists() else 0
    con = get_db()
    con.execute("VACUUM")
    con.commit()
    size_after = db_path.stat().st_size if db_path.exists() else 0
    saved_mb = round((size_before - size_after) / (1024 * 1024), 2)
    return {
        "size_before_mb": round(size_before / (1024 * 1024), 2),
        "size_after_mb": round(size_after / (1024 * 1024), 2),
        "saved_mb": saved_mb,
    }


def analyze_database() -> dict:
    from core.services_core.db_state import get_db

    con = get_db()
    con.execute("ANALYZE")
    con.commit()
    return {"message": "ANALYZE 完了"}
