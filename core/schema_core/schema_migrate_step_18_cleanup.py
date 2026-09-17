"""Schema migration step 18: garbage tag cleanup."""

import contextlib
import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_18(con: sqlite3.Connection) -> None:
    """Garbage tag cleanup + prompt_library orphan fix.

    BUG-33: LBW numeric remnants
    BUG-36: BREAK tags
    BUG-37: NAI ``::`` remnants
    BUG-38: Colon-prefix tags
    BUG-39: Overly long tags (>80 chars)
    BUG-42: prompt_library orphan source_file_id
    BUG-43: prompt_library_folder_items orphan records
    BUG-44: Brace emphasis remnants
    """
    logger.info("  -> Migration 18: Garbage tag cleanup + prompt_library orphan fix")

    garbage_ids = _collect_migration_18_garbage_ids(con)
    if garbage_ids:
        _delete_tag_ids(con, garbage_ids, "Cleaned")
    else:
        logger.info("     No garbage tags found")

    _nullify_orphan_prompt_library_sources(con)
    _delete_orphan_prompt_library_folder_items(con)
    _cleanup_orphan_tags(con)
    set_schema_version(con, 18, "Garbage tag cleanup + prompt_library orphan fix")


def _collect_migration_18_garbage_ids(con: sqlite3.Connection) -> set[int]:
    patterns = [
        "tag = 'break'",
        "tag LIKE ':%'",
        "LENGTH(tag) > 80",
        "tag GLOB '[0-9]*' AND LENGTH(tag) <= 5 AND tag NOT GLOB '*[a-zA-Z_]*'",
        "tag LIKE '%>'  AND LENGTH(tag) <= 10 AND tag NOT GLOB '*[a-zA-Z_]*'",
        "tag LIKE '[%'  AND tag NOT LIKE '[%]%'",
        "tag LIKE '{{%' OR tag LIKE '%}}'",
        "tag LIKE '::%'",
    ]
    garbage_ids: set[int] = set()
    for pattern in patterns:
        rows = con.execute(f"SELECT id FROM tags WHERE {pattern}").fetchall()
        garbage_ids.update(row[0] for row in rows)
    return garbage_ids


def _delete_tag_ids(con: sqlite3.Connection, garbage_ids: set[int], action: str) -> None:
    placeholders = ",".join("?" * len(garbage_ids))
    ids = list(garbage_ids)
    deleted_ft = con.execute(
        f"DELETE FROM file_tags WHERE tag_id IN ({placeholders})",
        ids,
    ).rowcount
    deleted_t = con.execute(
        f"DELETE FROM tags WHERE id IN ({placeholders})",
        ids,
    ).rowcount
    logger.info("     %s %d garbage tags, %d file_tags", action, deleted_t, deleted_ft)


def _nullify_orphan_prompt_library_sources(con: sqlite3.Connection) -> None:
    with contextlib.suppress(Exception):
        con.execute(
            """
            UPDATE prompt_library SET source_file_id = NULL
            WHERE source_file_id IS NOT NULL
            AND source_file_id NOT IN (SELECT id FROM files)
            """
        )


def _delete_orphan_prompt_library_folder_items(con: sqlite3.Connection) -> None:
    with contextlib.suppress(Exception):
        con.execute(
            """
            DELETE FROM prompt_library_folder_items
            WHERE prompt_id NOT IN (SELECT id FROM prompt_library)
            """
        )


def _cleanup_orphan_tags(con: sqlite3.Connection) -> None:
    orphan_count = con.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM file_tags)"
    ).rowcount
    if orphan_count:
        logger.info("     Cleaned %d orphan tags", orphan_count)
