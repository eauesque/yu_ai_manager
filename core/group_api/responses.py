"""Pure-sync response builders for groups endpoints.

Routes call these via ``run_db_sync``. They handle the DB read and any
post-processing (e.g. cache-path checks for container_thumb_ids).
"""

from __future__ import annotations

from typing import Any

from core.services_core.db_api import get_readonly_db

_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def build_groups_index_response() -> dict[str, Any]:
    from core.files_core.groups_index import get_groups_index

    db = get_readonly_db()
    return get_groups_index(db)


def build_groups_index_warm_response() -> dict[str, Any]:
    from core.files_core.groups_index import get_groups_index

    db = get_readonly_db()
    get_groups_index(db)
    return {"ok": True}


def build_group_members_response(key: str) -> dict[str, Any]:
    from core.files_core.groups_index import get_groups_index

    db = get_readonly_db()
    index = get_groups_index(db)
    for groups in (index.get("folders", {}), index.get("zips", {})):
        if key in groups:
            entry = groups[key]
            return {"ids": entry.get("ids", []), "key": key}
    return {"ids": [], "key": key}


def build_container_thumb_ids_response(limit: int = 500) -> dict[str, Any]:
    from core.files_core.groups_index import get_all_rep_ids, get_groups_index
    from core.files_core.thumbnail_common import cache_path_for_source, ensure_thumbnail_cache_dir

    db = get_readonly_db()
    index = get_groups_index(db)
    rep_ids = get_all_rep_ids(index)
    if not rep_ids:
        return {"ids": [], "total": 0, "cached": 0}
    file_info: dict[int, tuple[str, int]] = {}
    for chunk in _chunks(rep_ids):
        placeholders = ",".join("?" for _ in chunk)
        rows = db.execute(
            f"SELECT id, path, mtime FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        for row in rows:
            file_info[row["id"]] = (row["path"], row["mtime"])
    cache_dir = ensure_thumbnail_cache_dir()
    ids: list[int] = []
    cached = 0
    for fid in rep_ids:
        info = file_info.get(fid)
        if not info:
            continue
        cp = cache_path_for_source(cache_dir, info[0], info[1])
        if cp.exists():
            cached += 1
        else:
            ids.append(fid)
            if len(ids) >= limit:
                break
    return {"ids": ids, "total": len(ids), "cached": cached}
