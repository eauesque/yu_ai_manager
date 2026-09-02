"""DB CRUD for files table."""

import sqlite3

from core.schema_core.schema import CURRENT_PARSER_VERSION

_IN_CHUNK_SIZE = 500


def _chunks(items: list[str], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def get_file_row(con: sqlite3.Connection, path: str) -> tuple[int, int, int, int, str | None, int] | None:
    row = con.execute(
        "SELECT id, mtime, size, is_deleted, hash, COALESCE(parser_version, 1) FROM files WHERE path=?",
        (path,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1]), int(row[2]), int(row[3]), row[4], int(row[5])


def upsert_file(
    con: sqlite3.Connection,
    path: str,
    mtime: int,
    size: int,
    meta_source: str | None,
    content_hash: str | None = None,
    is_zip_member: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> int:
    existing = con.execute(
        """
        SELECT id, mtime, size, hash, meta_source, is_deleted, is_zip_member, parser_version, width, height
        FROM files WHERE path=?
        """,
        (path,),
    ).fetchone()
    if existing is not None:
        merged_hash = content_hash if content_hash is not None else existing[3]
        merged_width = width if width is not None else existing[8]
        merged_height = height if height is not None else existing[9]
        target_zip_member = 1 if is_zip_member else 0
        if (
            int(existing[1]) == int(mtime)
            and int(existing[2]) == int(size)
            and existing[4] == meta_source
            and int(existing[5]) == 0
            and int(existing[6]) == target_zip_member
            and int(existing[7]) == int(CURRENT_PARSER_VERSION)
            and existing[3] == merged_hash
            and existing[8] == merged_width
            and existing[9] == merged_height
        ):
            return int(existing[0])

    # Combine INSERT + SELECT into one query using RETURNING id
    row = con.execute(
        """INSERT INTO files(path, mtime, size, hash, meta_source, is_deleted, is_zip_member, parser_version, width, height)
           VALUES(?,?,?,?,?,0,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET
             mtime=excluded.mtime,
             size=excluded.size,
             hash=COALESCE(excluded.hash, files.hash),
             meta_source=excluded.meta_source,
             is_deleted=0,
             is_zip_member=excluded.is_zip_member,
             parser_version=excluded.parser_version,
             width=COALESCE(excluded.width, files.width),
             height=COALESCE(excluded.height, files.height)
           RETURNING id
        """,
        (
            path,
            mtime,
            size,
            content_hash,
            meta_source,
            1 if is_zip_member else 0,
            CURRENT_PARSER_VERSION,
            width,
            height,
        ),
    ).fetchone()
    return int(row[0])


def get_file_rows_batch(
    con: sqlite3.Connection, paths: list[str]
) -> dict[str, tuple[int, int, int, int, str | None, int]]:
    """Batch fetch file rows for multiple paths.

    Returns a dict mapping path -> (id, mtime, size, is_deleted, hash, parser_version).
    Missing paths are omitted from the result.
    """
    if not paths:
        return {}
    result: dict[str, tuple[int, int, int, int, str | None, int]] = {}
    for chunk in _chunks(list(dict.fromkeys(paths))):
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f"SELECT path, id, mtime, size, is_deleted, hash, COALESCE(parser_version, 1) "
            f"FROM files WHERE path IN ({placeholders})",
            chunk,
        )
        for row in rows:
            result[row[0]] = (int(row[1]), int(row[2]), int(row[3]), int(row[4]), row[5], int(row[6]))
    return result


def mark_deleted(con: sqlite3.Connection, path: str) -> None:
    con.execute("UPDATE files SET is_deleted=1 WHERE path=? AND is_deleted<>1", (path,))
