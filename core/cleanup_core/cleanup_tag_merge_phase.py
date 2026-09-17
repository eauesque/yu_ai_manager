"""Merge-phase operations for tag cleanup normalization."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .cleanup_tag_normalize import split_normalized_tag


def run_merge_phase(con: sqlite3.Connection, dry_run: bool = False) -> int:
    normalize_map = {}
    garbage_ids = []  # BUG-67: tags that normalize to nothing

    for tag_id, tag, namespace in con.execute("SELECT id, tag, namespace FROM tags"):
        parts = split_normalized_tag(tag)
        if not parts:
            # BUG-67: Tag normalizes to nothing — mark for removal
            garbage_ids.append((tag_id, tag))
            continue
        normalized = parts[0]
        key = (normalized, namespace or "")
        normalize_map.setdefault(key, []).append((tag_id, tag))

    merge_count = 0

    # BUG-67: Remove garbage tags (symbol-only, weight remnants, etc.)
    for tag_id, tag in garbage_ids:
        if not dry_run:
            con.execute("DELETE FROM file_tags WHERE tag_id=?", (tag_id,))
            con.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        merge_count += 1
        if merge_count <= 20:
            logger.info(f"    Removed garbage tag: '{tag}'")
    for (normalized_tag, namespace), tag_list in normalize_map.items():
        if len(tag_list) <= 1:
            tag_id, original_tag = tag_list[0]
            if original_tag != normalized_tag and not dry_run:
                existing = con.execute(
                    "SELECT id FROM tags WHERE tag=? AND namespace=?", (normalized_tag, namespace or "")
                ).fetchone()
                if existing and existing[0] != tag_id:
                    keep_id = existing[0]
                    con.execute(
                        """
                        UPDATE file_tags SET tag_id=?
                        WHERE tag_id=?
                        AND NOT EXISTS (
                            SELECT 1 FROM file_tags ft2
                            WHERE ft2.file_id=file_tags.file_id AND ft2.tag_id=?
                        )
                        """,
                        (keep_id, tag_id, keep_id),
                    )
                    con.execute("DELETE FROM file_tags WHERE tag_id=?", (tag_id,))
                    con.execute("DELETE FROM tags WHERE id=?", (tag_id,))
                    merge_count += 1
                    logger.info(f"    Merged '{original_tag}' -> existing '{normalized_tag}'")
                else:
                    con.execute("UPDATE tags SET tag=? WHERE id=?", (normalized_tag, tag_id))
                    merge_count += 1
                    logger.info(f"    Renamed '{original_tag}' -> '{normalized_tag}'")
            continue

        tag_usage = []
        for tag_id, original_tag in tag_list:
            count = con.execute("SELECT COUNT(*) FROM file_tags WHERE tag_id=?", (tag_id,)).fetchone()[0]
            tag_usage.append((tag_id, original_tag, count))

        tag_usage.sort(key=lambda x: x[2], reverse=True)
        keep_id = tag_usage[0][0]
        if not dry_run:
            try:
                con.execute("UPDATE tags SET tag=? WHERE id=?", (normalized_tag, keep_id))
            except Exception as exc:
                logger.debug("Failed to rename tag %s: %s", keep_id, exc)

        for tag_id, original_tag, count in tag_usage[1:]:
            if not dry_run:
                con.execute(
                    """
                    UPDATE file_tags
                    SET tag_id=?
                    WHERE tag_id=?
                    AND NOT EXISTS (
                        SELECT 1 FROM file_tags ft2
                        WHERE ft2.file_id=file_tags.file_id
                        AND ft2.tag_id=?
                    )
                    """,
                    (keep_id, tag_id, keep_id),
                )
                con.execute("DELETE FROM file_tags WHERE tag_id=?", (tag_id,))
                con.execute("DELETE FROM tags WHERE id=?", (tag_id,))

            merge_count += 1
            if count > 0:
                logger.info(f"    Merging '{original_tag}' -> '{normalized_tag}' ({count} files)")

    return merge_count


def cleanup_orphan_tags(con: sqlite3.Connection) -> int:
    orphan_count = con.execute(
        """
        DELETE FROM tags WHERE id NOT IN (
            SELECT DISTINCT tag_id FROM file_tags
        )
        """
    ).rowcount
    if orphan_count > 0:
        logger.info(f"    Cleaned {orphan_count} orphan tags")
    return orphan_count
