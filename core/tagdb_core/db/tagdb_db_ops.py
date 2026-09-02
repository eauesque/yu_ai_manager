"""DB upsert/query helpers for tagdb."""

import json
import sqlite3
from collections.abc import Sequence

from core.tagdb_core.db.tagdb_db_model_info import extract_model_info
from core.tagdb_core.db_schema.tagdb_db_schema_constants import CURRENT_PARSER_VERSION
from core.tagdb_prompt import TemplateToken


def get_file_row(con: sqlite3.Connection, path: str) -> tuple[int, int, int, int, str | None, int] | None:
    """Return (id, mtime, size, is_deleted, hash, parser_version)."""
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
    content_hash: str | None,
    is_zip_member: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> int:
    existing = con.execute(
        """
        SELECT
          id, mtime, size, hash, meta_source, is_deleted,
          is_zip_member, COALESCE(parser_version, 1), width, height
        FROM files
        WHERE path=?
        """,
        (path,),
    ).fetchone()
    if existing is not None:
        file_id = int(existing[0])
        target_hash = content_hash if content_hash is not None else existing[3]
        target_width = width if width is not None else existing[8]
        target_height = height if height is not None else existing[9]
        if (
            int(existing[1]) == int(mtime)
            and int(existing[2]) == int(size)
            and ((str(existing[3]) if existing[3] is not None else None) == (str(target_hash) if target_hash is not None else None))
            and ((str(existing[4]) if existing[4] is not None else None) == (str(meta_source) if meta_source is not None else None))
            and int(existing[5]) == 0
            and int(existing[6]) == (1 if is_zip_member else 0)
            and int(existing[7]) == int(CURRENT_PARSER_VERSION)
            and ((int(existing[8]) if existing[8] is not None else None) == (int(target_width) if target_width is not None else None))
            and ((int(existing[9]) if existing[9] is not None else None) == (int(target_height) if target_height is not None else None))
        ):
            return file_id

    # Combine INSERT + SELECT into one query using RETURNING id (eliminates N+1)
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
           RETURNING id""",
        (path, mtime, size, content_hash, meta_source, 1 if is_zip_member else 0, CURRENT_PARSER_VERSION, width, height),
    ).fetchone()
    return int(row[0])


def clear_tags_for_file(con: sqlite3.Connection, file_id: int) -> None:
    con.execute("DELETE FROM file_tags WHERE file_id=?", (file_id,))


def upsert_tag(
    con: sqlite3.Connection,
    namespace: str | None,
    tag: str,
    *,
    first_seen_mtime: int | None = None,
) -> int:
    # SELECT-first avoids no-op UPDATE on repeated tag reuse.
    row = con.execute(
        "SELECT id, first_seen_mtime FROM tags WHERE tag=? AND namespace IS ?",
        (tag, namespace),
    ).fetchone()
    if row is not None:
        tag_id = int(row[0])
        existing_mtime = row[1]
        if first_seen_mtime is not None and (
            existing_mtime is None or int(first_seen_mtime) < int(existing_mtime)
        ):
            con.execute(
                """
                UPDATE tags
                SET first_seen_mtime=?
                WHERE id=?
                  AND (first_seen_mtime IS NULL OR first_seen_mtime>?)
                """,
                (int(first_seen_mtime), tag_id, int(first_seen_mtime)),
            )
        return tag_id

    con.execute(
        "INSERT INTO tags(tag, namespace, first_seen_mtime) VALUES(?,?,?)",
        (tag, namespace, first_seen_mtime),
    )
    return int(con.execute("SELECT last_insert_rowid()").fetchone()[0])


def insert_file_tag(con: sqlite3.Connection, file_id: int, tag_id: int, weight: float) -> None:
    con.execute(
        """INSERT INTO file_tags(file_id, tag_id, weight) VALUES(?,?,?)
           ON CONFLICT(file_id, tag_id) DO UPDATE SET weight=excluded.weight
        """,
        (file_id, tag_id, weight),
    )


def upsert_template(
    con: sqlite3.Connection,
    file_id: int,
    raw_prompt: str | None,
    raw_negative: str | None,
    fmt: str,
    raw_meta_json: str | None,
) -> int:
    model_name, model_hash = extract_model_info(raw_meta_json, fmt)
    existing = con.execute(
        """
        SELECT id, raw_prompt, raw_negative, format, raw_meta_json, model_name, model_hash
        FROM templates
        WHERE file_id=?
        """,
        (file_id,),
    ).fetchone()
    if existing is not None:  # noqa: SIM102
        if (
            ((str(existing[1]) if existing[1] is not None else None) == (str(raw_prompt) if raw_prompt is not None else None))
            and ((str(existing[2]) if existing[2] is not None else None) == (str(raw_negative) if raw_negative is not None else None))
            and str(existing[3] or "") == str(fmt or "")
            and ((str(existing[4]) if existing[4] is not None else None) == (str(raw_meta_json) if raw_meta_json is not None else None))
            and ((str(existing[5]) if existing[5] is not None else None) == (str(model_name) if model_name is not None else None))
            and ((str(existing[6]) if existing[6] is not None else None) == (str(model_hash) if model_hash is not None else None))
        ):
            return int(existing[0])

    # Combine INSERT + SELECT into one query using RETURNING id (eliminates N+1)
    row = con.execute(
        """INSERT INTO templates(file_id, raw_prompt, raw_negative, format, raw_meta_json, model_name, model_hash)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(file_id) DO UPDATE SET
               raw_prompt=excluded.raw_prompt,
               raw_negative=excluded.raw_negative,
               format=excluded.format,
               raw_meta_json=excluded.raw_meta_json,
               model_name=excluded.model_name,
               model_hash=excluded.model_hash
           RETURNING id""",
        (file_id, raw_prompt, raw_negative, fmt, raw_meta_json, model_name, model_hash),
    ).fetchone()
    return int(row[0])


def replace_template_tokens(con: sqlite3.Connection, template_id: int, tokens: Sequence[TemplateToken]) -> None:
    incoming = [
        (t.token_type, json.dumps(t.payload, ensure_ascii=False), int(t.position))
        for t in tokens
    ]
    existing = con.execute(
        """
        SELECT token_type, payload, position
        FROM template_tokens
        WHERE template_id=?
        ORDER BY position, id
        """,
        (template_id,),
    ).fetchall()
    existing_rows = [(str(r[0]), str(r[1]), int(r[2])) for r in existing]
    if existing_rows == incoming:
        return

    con.execute("DELETE FROM template_tokens WHERE template_id=?", (template_id,))
    if tokens:
        # Use executemany() to batch individual INSERTs in the loop
        con.executemany(
            "INSERT INTO template_tokens(template_id, token_type, payload, position) VALUES(?,?,?,?)",
            [(template_id, token_type, payload, position) for token_type, payload, position in incoming],
        )
