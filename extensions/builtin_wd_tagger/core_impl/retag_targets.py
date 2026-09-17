"""Target enumeration for WD retag jobs."""

from __future__ import annotations

from typing import Any

from core.services_core.wd_dict_resolver import resolve_model_id_readonly

from .retag_db_ops import get_read_db

IN_LIST_CHUNK = 500


def _normalize_scan_root(scan_root: str) -> str:
    return scan_root.rstrip("/\\")


def _like_escape(value: str) -> str:
    return value.replace("~", "~~").replace("%", "~%").replace("_", "~_")


def _scan_root_like_patterns(scan_root: str) -> tuple[str, str]:
    root = _normalize_scan_root(scan_root)
    fwd = _like_escape(root.replace("\\", "/").rstrip("/"))
    bck = _like_escape(root.replace("/", "\\").rstrip("\\"))
    return f"{fwd}/%", f"{bck}\\%"


def enumerate_targets(
    scope: str,
    *,
    model_id: str,
    file_ids: list[int] | None = None,
    scan_root: str = "",
    force: bool = False,
    limit: int = 0,
    search_fn=None,
    query_params: dict[str, Any] | None = None,
) -> list[int]:
    con = get_read_db()
    if scope == "batch":
        if not file_ids:
            return []
        active = filter_active_in_order(con, file_ids)
        return active[:limit] if limit > 0 else active
    if scope == "backfill":
        return _enumerate_backfill(con, model_id, scan_root, force, limit)
    if scope == "query":
        if search_fn is None:
            raise ValueError("scope=query requires search_fn")
        active = filter_active_in_order(con, list(search_fn(query_params or {})))
        return active[:limit] if limit > 0 else active
    raise ValueError(f"unknown scope={scope!r}")


def _enumerate_backfill(con, model_id: str, scan_root: str, force: bool, limit: int) -> list[int]:
    scan_root = _normalize_scan_root(scan_root)
    sql = "SELECT id FROM files WHERE is_deleted = 0"
    params: list[Any] = []
    if scan_root:
        sql += " AND (path LIKE ? ESCAPE '~' OR path LIKE ? ESCAPE '~')"
        params.extend(_scan_root_like_patterns(scan_root))
    if not force:
        mid = resolve_model_id_readonly(con, model_id)
        if mid is None:
            mid = -1
        sql += (
            " AND NOT EXISTS ("
            "  SELECT 1 FROM file_wd_tags fwt"
            "  WHERE fwt.file_id = files.id AND fwt.model_id = ?"
            ")"
        )
        params.append(mid)
    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    return [row[0] for row in con.execute(sql, params)]


def filter_active_in_order(con, file_ids: list[int]) -> list[int]:
    if not file_ids:
        return []
    active: set[int] = set()
    for i in range(0, len(file_ids), IN_LIST_CHUNK):
        chunk = file_ids[i : i + IN_LIST_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = con.execute(
            f"SELECT id FROM files WHERE id IN ({placeholders}) AND is_deleted = 0",
            chunk,
        )
        for row in rows:
            active.add(row[0])
    return [fid for fid in file_ids if fid in active]
