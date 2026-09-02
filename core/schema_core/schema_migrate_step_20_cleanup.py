"""Schema migration step 20: garbage cleanup round 2."""

import json
import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_20(con: sqlite3.Connection) -> None:
    """Comprehensive garbage tag cleanup round 2 + ComfyUI resolution rework."""
    logger.info("  -> Migration 20: Comprehensive garbage cleanup round 2")

    _backfill_comfy_resolutions(con)
    garbage_ids = _collect_garbage_ids(con)
    if garbage_ids:
        _delete_tag_ids(con, garbage_ids)

    _fix_duplicate_namespace_prefixes(con)
    _trim_comma_wrapped_tags(con)
    _trim_comma_wrapped_namespaces(con)
    _nullify_long_namespaces(con)
    _round_file_tag_weights(con)
    _cleanup_empty_tags(con)
    _merge_duplicate_tags(con)
    _cleanup_orphan_tags(con)
    set_schema_version(con, 20, "Comprehensive garbage cleanup round 2")


def _backfill_comfy_resolutions(con: sqlite3.Connection) -> None:
    rows = con.execute(
        """
        SELECT t.id, t.raw_meta_json FROM templates t
        JOIN files f ON f.id = t.id
        WHERE f.width IS NULL AND f.height IS NULL
        AND (f.meta_source LIKE 'comfy%' OR f.meta_source = 'comfyui')
        AND t.raw_meta_json IS NOT NULL
        """
    ).fetchall()

    res_count = 0
    for file_id, raw_meta_json in rows:
        if _update_resolution_from_comfy_json(con, file_id, raw_meta_json):
            res_count += 1
    if res_count:
        logger.info("     BUG-40: Backfilled %d additional ComfyUI resolutions", res_count)


def _update_resolution_from_comfy_json(
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

    width = obj.get("width")
    height = obj.get("height")
    if _is_positive_dimension(width, height):
        con.execute(
            "UPDATE files SET width=?, height=? WHERE id=?",
            (int(width), int(height), file_id),
        )
        return True

    for node in obj.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        node_width = inputs.get("width")
        node_height = inputs.get("height")
        if _is_positive_dimension(node_width, node_height):
            con.execute(
                "UPDATE files SET width=?, height=? WHERE id=?",
                (int(node_width), int(node_height), file_id),
            )
            return True
    return False


def _is_positive_dimension(width, height) -> bool:
    return (
        isinstance(width, (int, float))
        and isinstance(height, (int, float))
        and width > 0
        and height > 0
    )


def _collect_garbage_ids(con: sqlite3.Connection) -> set[int]:
    clauses = [
        "tag LIKE '%' || '{{' || '%' OR tag LIKE '%' || '}}' || '%'",
        "tag = ':'",
        "namespace LIKE 'adetailer%'",
        "namespace LIKE '%<lora%' OR namespace LIKE '%<lyco%'",
        "tag LIKE '%:%>' AND tag NOT LIKE '<%>%'",
        "tag LIKE '%${%'",
    ]
    garbage_ids: set[int] = set()
    for clause in clauses:
        rows = con.execute(f"SELECT id FROM tags WHERE {clause}").fetchall()
        garbage_ids.update(row[0] for row in rows)
    return garbage_ids


def _delete_tag_ids(con: sqlite3.Connection, garbage_ids: set[int]) -> None:
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
    logger.info("     Deleted %d garbage tags, %d file_tags", deleted_t, deleted_ft)


def _fix_duplicate_namespace_prefixes(con: sqlite3.Connection) -> None:
    rows = con.execute(
        """
        SELECT id, tag, namespace FROM tags
        WHERE namespace IS NOT NULL AND tag LIKE namespace || ':%'
        """
    ).fetchall()
    fixed = 0
    for tag_id, tag, namespace in rows:
        new_tag = tag[len(namespace) + 1 :].strip()
        if _merge_or_replace_tag(con, tag_id, namespace, new_tag):
            fixed += 1
    if fixed:
        logger.info("     BUG-41: Fixed %d duplicated namespace prefixes", fixed)


def _trim_comma_wrapped_tags(con: sqlite3.Connection) -> None:
    rows = con.execute(
        "SELECT id, tag, namespace FROM tags WHERE tag LIKE '%,' OR tag LIKE ',%'"
    ).fetchall()
    fixed = 0
    for tag_id, tag, namespace in rows:
        new_tag = tag.strip(",").strip()
        if new_tag == tag:
            continue
        if _merge_or_replace_tag(con, tag_id, namespace, new_tag):
            fixed += 1
    if fixed:
        logger.info("     BUG-50: Trimmed commas from %d tags", fixed)


def _merge_or_replace_tag(
    con: sqlite3.Connection,
    tag_id: int,
    namespace: str | None,
    new_tag: str,
) -> bool:
    if not new_tag:
        _delete_tag(con, tag_id)
        return True

    existing = con.execute(
        "SELECT id FROM tags WHERE tag = ? AND namespace IS ? LIMIT 1",
        (new_tag, namespace),
    ).fetchone()
    if existing:
        _merge_tag_into(con, tag_id, existing[0])
    else:
        con.execute("UPDATE tags SET tag = ? WHERE id = ?", (new_tag, tag_id))
    return True


def _delete_tag(con: sqlite3.Connection, tag_id: int) -> None:
    con.execute("DELETE FROM file_tags WHERE tag_id = ?", (tag_id,))
    con.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


def _merge_tag_into(con: sqlite3.Connection, old_tag_id: int, keep_id: int) -> None:
    con.execute(
        "UPDATE file_tags SET tag_id = ? "
        "WHERE tag_id = ? AND NOT EXISTS ("
        "  SELECT 1 FROM file_tags ft2 "
        "  WHERE ft2.file_id = file_tags.file_id AND ft2.tag_id = ?)",
        (keep_id, old_tag_id, keep_id),
    )
    _delete_tag(con, old_tag_id)


def _trim_comma_wrapped_namespaces(con: sqlite3.Connection) -> None:
    con.execute(
        """
        UPDATE tags SET namespace = trim(namespace, ',')
        WHERE namespace IS NOT NULL AND (namespace LIKE '%,' OR namespace LIKE ',%')
        """
    )


def _nullify_long_namespaces(con: sqlite3.Connection) -> None:
    fixed = con.execute(
        """
        UPDATE tags SET namespace = NULL
        WHERE namespace IS NOT NULL AND LENGTH(namespace) > 50
        """
    ).rowcount
    if fixed:
        logger.info("     BUG-51: Nullified %d overly long namespaces", fixed)


def _round_file_tag_weights(con: sqlite3.Connection) -> None:
    fixed = con.execute(
        """
        UPDATE file_tags SET weight = round(weight, 4)
        WHERE weight != round(weight, 4)
        """
    ).rowcount
    if fixed:
        logger.info("     BUG-54: Rounded %d imprecise weights", fixed)


def _cleanup_empty_tags(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM file_tags WHERE tag_id IN (SELECT id FROM tags WHERE tag = '')")
    con.execute("DELETE FROM tags WHERE tag = ''")


def _merge_duplicate_tags(con: sqlite3.Connection) -> None:
    rows = con.execute(
        "SELECT tag, namespace, MIN(id) AS keep_id, GROUP_CONCAT(id) AS all_ids "
        "FROM tags GROUP BY tag, namespace HAVING COUNT(*) > 1"
    ).fetchall()
    merged = 0
    for _tag, _namespace, keep_id, all_ids_str in rows:
        dup_ids = [int(tag_id) for tag_id in all_ids_str.split(",") if int(tag_id) != keep_id]
        for dup_id in dup_ids:
            _merge_tag_into(con, dup_id, keep_id)
            merged += 1
    if merged:
        logger.info("     Merged %d tags that became duplicates", merged)


def _cleanup_orphan_tags(con: sqlite3.Connection) -> None:
    orphan_count = con.execute(
        "DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM file_tags)"
    ).rowcount
    if orphan_count:
        logger.info("     Cleaned %d orphan tags", orphan_count)
