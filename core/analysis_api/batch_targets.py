"""Batch target resolution helpers for analysis API."""

from core.services_core.db_api import get_raw_db


def resolve_batch_targets(file_ids: list, limit: int, scan_root: str = ""):
    if file_ids:
        return file_ids
    con = get_raw_db()

    where = "f.is_deleted = 0 AND a.id IS NULL"
    params: list = []

    if scan_root:
        # Support both Windows \ and Unix / (LIKE + COLLATE NOCASE)
        fwd = scan_root.replace("\\", "/").rstrip("/")
        bck = scan_root.replace("/", "\\").rstrip("\\")
        where += " AND (f.path LIKE ? COLLATE NOCASE OR f.path LIKE ? COLLATE NOCASE)"
        params.extend([fwd + "/%", bck + "\\%"])

    sql = f"""
        SELECT f.id FROM files f
        LEFT JOIN analysis a ON a.file_id = f.id
        WHERE {where}
        ORDER BY f.mtime DESC
    """

    if limit > 0:
        sql += " LIMIT ?"
        params.append(limit)

    rows = con.execute(sql, params)
    return [r[0] for r in rows]
