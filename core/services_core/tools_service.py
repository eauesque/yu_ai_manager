"""Synchronous helpers for tools-related cache and index operations."""

from __future__ import annotations

import json


def _clear_thumbnail_cache_entries_write() -> None:
    from core.services_core.db_api import get_db

    con = get_db()
    con.execute("DELETE FROM cache_entry WHERE kind='thumbnail'")
    con.commit()


def clear_thumbnail_cache_entries() -> None:
    from core.services_core.db_write import submit_db_write

    submit_db_write(_clear_thumbnail_cache_entries_write)


def rebuild_groups_index_cache() -> dict:
    from core.files_core.groups_index import (
        _CACHE_PATH,
        build_groups_index,
        invalidate_cache,
    )
    from core.services_core.db_api import get_readonly_db

    invalidate_cache()
    index = build_groups_index(get_readonly_db())
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return {
        "status": "rebuilt",
        "folders": len(index.get("folders", {})),
        "zips": len(index.get("zips", {})),
        "file_count": index.get("file_count", 0),
    }
