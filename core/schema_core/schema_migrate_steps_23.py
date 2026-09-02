"""Schema migration step 23: BUG-63/64/65/66 data fixes."""

import json as _json
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version

_RE_NAI_SOURCE = re.compile(r"^(.+?)\s+([A-Fa-f0-9]{6,})$")


def apply_migration_23(con: sqlite3.Connection) -> None:
    """BUG-63/64/65/66 data fixes.

    BUG-65: NAI v4 model_name backfill from raw_meta_json Source key.
    BUG-66: Zombie tags cleanup (tags with no file_tags references).
    BUG-63: prompt_library_tag_map orphan rows cleanup.
    BUG-64: favorites table rebuild with collection_id FK constraint.
    """
    logger.info("  -> Migration 23: BUG-63/64/65/66 data fixes")

    # --- BUG-65: NAI v4 model_name backfill ---
    rows_65 = con.execute("""
        SELECT t.id, t.raw_meta_json
        FROM templates t
        JOIN files f ON t.file_id = f.id
        WHERE f.meta_source IN ('novelai_v4_png', 'novelai_v4_webp')
          AND t.model_name IS NULL
          AND t.raw_meta_json IS NOT NULL
    """).fetchall()

    fixed_65 = 0
    for tid, raw_meta_json in rows_65:
        try:
            meta = _json.loads(raw_meta_json)
            if not isinstance(meta, dict):
                continue
            source = meta.get("Source")
            software = meta.get("Software")
            if not source or not isinstance(software, str) or "NovelAI" not in software:
                continue
            source = source.strip()
            if not source:
                continue
            m = _RE_NAI_SOURCE.search(source)
            if m:
                model_name = m.group(1).strip()
                model_hash = m.group(2).strip()
            else:
                model_name = source
                model_hash = None
            con.execute(
                "UPDATE templates SET model_name=?, model_hash=? WHERE id=?",
                (model_name, model_hash, tid),
            )
            fixed_65 += 1
        except (_json.JSONDecodeError, TypeError):
            continue

    if fixed_65:
        logger.info(f"     BUG-65: Backfilled model_name for {fixed_65} NAI v4 templates")
    else:
        logger.info("     BUG-65: No NAI v4 templates with missing model_name")

    # --- BUG-66: Zombie tags cleanup ---
    zombie_count = con.execute(
        "DELETE FROM tags WHERE id NOT IN "
        "(SELECT DISTINCT tag_id FROM file_tags)"
    ).rowcount
    if zombie_count:
        logger.info(f"     BUG-66: Deleted {zombie_count} zombie tags")
    else:
        logger.info("     BUG-66: No zombie tags found")

    # --- BUG-63: prompt_library_tag_map orphan rows ---
    # Tables may not exist if prompt library was never initialized
    try:
        orphan_63 = con.execute(
            "DELETE FROM prompt_library_tag_map "
            "WHERE prompt_id NOT IN (SELECT id FROM prompt_library) "
            "   OR tag_id NOT IN (SELECT id FROM prompt_library_tags)"
        ).rowcount
        if orphan_63:
            logger.info(f"     BUG-63: Deleted {orphan_63} orphan prompt_library_tag_map rows")
        else:
            logger.info("     BUG-63: No orphan prompt_library_tag_map rows")
    except Exception:
        logger.info("     BUG-63: prompt_library tables not present, skipped")

    # --- BUG-64: favorites FK constraint on collection_id ---
    logger.info("     BUG-64: Rebuilding favorites table with collection_id FK")
    # Drop FTS triggers before DROP/RENAME to avoid SQLite trigger validation
    # errors when referenced columns (char_positive) don't exist yet.
    for trig in ("templates_ai", "templates_ad", "templates_au"):
        con.execute(f"DROP TRIGGER IF EXISTS {trig}")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS favorites_new (
          file_id INTEGER NOT NULL,
          collection_id INTEGER NOT NULL DEFAULT 1,
          added_at INTEGER NOT NULL,
          PRIMARY KEY (file_id, collection_id),
          FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
          FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
        );
        INSERT OR IGNORE INTO favorites_new (file_id, collection_id, added_at)
          SELECT file_id, collection_id, added_at FROM favorites
          WHERE collection_id IN (SELECT id FROM collections);
        DROP TABLE favorites;
        ALTER TABLE favorites_new RENAME TO favorites;
    """)
    logger.info("     BUG-64: favorites table rebuilt with collection_id FK")

    set_schema_version(con, 23, "BUG-63/64/65/66 data fixes")
