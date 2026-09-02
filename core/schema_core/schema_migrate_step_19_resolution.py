"""Schema migration step 19: ComfyUI resolution backfill."""

import json
import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_19(con: sqlite3.Connection) -> None:
    """Backfill width/height for ComfyUI files from raw_meta_json."""
    logger.info("  -> Migration 19: Backfilling ComfyUI resolutions from node graph")

    rows = con.execute(
        """
        SELECT t.id, t.raw_meta_json FROM templates t
        JOIN files f ON f.id = t.id
        WHERE f.width IS NULL AND f.height IS NULL
        AND f.meta_source LIKE 'comfy_%'
        AND t.raw_meta_json IS NOT NULL
        """
    ).fetchall()

    count = 0
    for file_id, raw_meta_json in rows:
        if _backfill_comfy_node_graph(con, file_id, raw_meta_json):
            count += 1

    logger.info("     Backfilled %d ComfyUI resolutions", count)
    set_schema_version(con, 19, f"ComfyUI resolution backfill ({count} files)")


def _backfill_comfy_node_graph(
    con: sqlite3.Connection,
    file_id: int,
    raw_meta_json: str,
) -> bool:
    try:
        obj = json.loads(raw_meta_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False

    if not isinstance(obj, dict):
        return False

    for node in obj.values():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        if cls not in ("EmptyLatentImage", "EmptySD3LatentImage"):
            continue
        inputs = node.get("inputs", {})
        width = inputs.get("width")
        height = inputs.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            con.execute(
                "UPDATE files SET width=?, height=? WHERE id=?",
                (int(width), int(height), file_id),
            )
            return True
    return False
