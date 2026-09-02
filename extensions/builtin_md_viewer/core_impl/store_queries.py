"""Query and row-shaping helpers for MD Viewer store."""

from __future__ import annotations

from typing import Any

_IN_CHUNK_SIZE = 500


def _chunks(items: list[int], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def get_md_file(con, file_id: int) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT id, path, mtime, size, title, content, lang, indexed_at "
        "FROM md_files WHERE id = ? AND is_deleted = 0",
        (file_id,),
    ).fetchone()
    if not row:
        return None
    return row_to_dict(row)


def get_md_file_by_path(con, path: str) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT id, path, mtime, size, title, content, lang, indexed_at "
        "FROM md_files WHERE path = ? AND is_deleted = 0",
        (path,),
    ).fetchone()
    if not row:
        return None
    return row_to_dict(row)


def search_md_files(
    con,
    query: str,
    path_filter: str = "",
    lang_filter: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not query.strip():
        return list_md_files(
            con,
            path_filter=path_filter,
            lang_filter=lang_filter,
            limit=limit,
            offset=offset,
        )

    sql = """
        SELECT m.id, m.path, m.mtime, m.size, m.title, m.lang, m.indexed_at,
               bm25(md_files_fts) AS score
        FROM md_files_fts f
        JOIN md_files m ON m.id = f.rowid
        WHERE md_files_fts MATCH ? AND m.is_deleted = 0
    """
    params: list = [query]
    if path_filter:
        sql += " AND m.path LIKE ?"
        params.append(f"%{path_filter}%")
    if lang_filter:
        sql += " AND m.lang = ?"
        params.append(lang_filter)
    sql += " ORDER BY score LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = con.execute(sql, params)
    return [row_to_meta_dict(row) for row in rows]


def list_md_files(
    con,
    path_filter: str = "",
    lang_filter: str = "",
    sort: str = "mtime",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    allowed_sorts = {"mtime", "title", "size", "path"}
    sort_col = sort if sort in allowed_sorts else "mtime"
    order_dir = "ASC" if order.lower() == "asc" else "DESC"

    sql = (
        "SELECT id, path, mtime, size, title, lang, indexed_at "
        "FROM md_files WHERE is_deleted = 0"
    )
    params: list = []
    if path_filter:
        sql += " AND path LIKE ?"
        params.append(f"%{path_filter}%")
    if lang_filter:
        sql += " AND lang = ?"
        params.append(lang_filter)
    sql += f" ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = con.execute(sql, params)
    return [row_to_meta_dict(row) for row in rows]


def count_md_files(con, query: str = "", path_filter: str = "", lang_filter: str = "") -> int:
    if query.strip():
        sql = """
            SELECT COUNT(*) FROM md_files_fts f
            JOIN md_files m ON m.id = f.rowid
            WHERE md_files_fts MATCH ? AND m.is_deleted = 0
        """
        params: list = [query]
        if path_filter:
            sql += " AND m.path LIKE ?"
            params.append(f"%{path_filter}%")
        if lang_filter:
            sql += " AND m.lang = ?"
            params.append(lang_filter)
        row = con.execute(sql, params).fetchone()
        return row[0] if row else 0

    sql = "SELECT COUNT(*) FROM md_files WHERE is_deleted = 0"
    params = []
    if path_filter:
        sql += " AND path LIKE ?"
        params.append(f"%{path_filter}%")
    if lang_filter:
        sql += " AND lang = ?"
        params.append(lang_filter)
    row = con.execute(sql, params).fetchone()
    return row[0] if row else 0


def get_languages(con) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT lang, COUNT(*) AS cnt FROM md_files "
        "WHERE is_deleted = 0 AND lang != '' "
        "GROUP BY lang ORDER BY cnt DESC"
    )
    return [{"lang": row[0], "count": row[1]} for row in rows]


def mark_missing_deleted(con, found_paths: set) -> int:
    rows = con.execute("SELECT id, path FROM md_files WHERE is_deleted = 0")
    missing_ids = []
    for row in rows:
        path = row["path"] if hasattr(row, "keys") else row[1]
        row_id = row["id"] if hasattr(row, "keys") else row[0]
        if path not in found_paths:
            missing_ids.append(row_id)
    if not missing_ids:
        return 0
    for chunk in _chunks(missing_ids):
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"UPDATE md_files SET is_deleted = 1 WHERE id IN ({placeholders})",
            chunk,
        )
    con.commit()
    return len(missing_ids)


def row_to_dict(row) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0],
        "path": row[1],
        "mtime": row[2],
        "size": row[3],
        "title": row[4],
        "content": row[5],
        "lang": row[6],
        "indexed_at": row[7],
    }


def row_to_meta_dict(row) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return dict(row)
    return {
        "id": row[0],
        "path": row[1],
        "mtime": row[2],
        "size": row[3],
        "title": row[4],
        "lang": row[5],
        "indexed_at": row[6],
    }
