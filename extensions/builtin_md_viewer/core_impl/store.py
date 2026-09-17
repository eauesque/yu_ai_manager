from __future__ import annotations

"""MD Viewer store: SQL CRUD layer.

Self-initialization pattern: auto-creates tables via ensure_tables().
FTS5 トリガーはマイグレーション v31 で作成済みだが、
ensure_tables() でも CREATE IF NOT EXISTS で安全に再実行可能。
"""

import sqlite3

from core.services_core.db_write import submit_db_write
from core.services_core.md_viewer_store_service import (
    mark_missing_deleted_rows,
    upsert_md_file_row,
)

from .store_queries import (
    count_md_files as _count_md_files,
)
from .store_queries import (
    get_languages as _get_languages,
)
from .store_queries import (
    get_md_file as _get_md_file,
)
from .store_queries import (
    get_md_file_by_path as _get_md_file_by_path,
)
from .store_queries import (
    list_md_files as _list_md_files,
)
from .store_queries import (
    search_md_files as _search_md_files,
)
from .store_schema import ensure_tables


def upsert_md_file(
    con: sqlite3.Connection | None,
    path: str,
    mtime: float,
    size: int,
    title: str,
    content: str,
    lang: str = "",
) -> int:
    """Insert or update an MD file and return the row ID."""
    if con is not None:
        return upsert_md_file_row(path, mtime, size, title, content, lang=lang, con=con)
    return submit_db_write(
        lambda: upsert_md_file_row(path, mtime, size, title, content, lang=lang)
    )


def get_md_file(con: sqlite3.Connection, file_id: int):
    ensure_tables(con)
    return _get_md_file(con, file_id)


def get_md_file_by_path(con: sqlite3.Connection, path: str):
    ensure_tables(con)
    return _get_md_file_by_path(con, path)


def search_md_files(
    con: sqlite3.Connection,
    query: str,
    path_filter: str = "",
    lang_filter: str = "",
    limit: int = 50,
    offset: int = 0,
):
    ensure_tables(con)
    return _search_md_files(
        con,
        query,
        path_filter=path_filter,
        lang_filter=lang_filter,
        limit=limit,
        offset=offset,
    )


def list_md_files(
    con: sqlite3.Connection,
    path_filter: str = "",
    lang_filter: str = "",
    sort: str = "mtime",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
):
    ensure_tables(con)
    return _list_md_files(
        con,
        path_filter=path_filter,
        lang_filter=lang_filter,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


def count_md_files(
    con: sqlite3.Connection,
    query: str = "",
    path_filter: str = "",
    lang_filter: str = "",
) -> int:
    ensure_tables(con)
    return _count_md_files(con, query=query, path_filter=path_filter, lang_filter=lang_filter)


def get_languages(con: sqlite3.Connection):
    ensure_tables(con)
    return _get_languages(con)


def mark_missing_deleted(con: sqlite3.Connection | None, found_paths: set) -> int:
    if con is not None:
        return mark_missing_deleted_rows(found_paths, con=con)
    return submit_db_write(lambda: mark_missing_deleted_rows(found_paths))

