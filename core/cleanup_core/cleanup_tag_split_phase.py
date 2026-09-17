"""Split-phase operations for tag cleanup normalization."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .cleanup_tag_normalize import split_normalized_tag


def run_split_phase(con: sqlite3.Connection, dry_run: bool = False) -> int:
    split_candidates: list[tuple[int, str, str | None, list[str]]] = []
    for tag_id, tag, namespace in con.execute("SELECT id, tag, namespace FROM tags"):
        parts = split_normalized_tag(tag)
        if len(parts) > 1:
            split_candidates.append((tag_id, tag, namespace, parts))

    split_count = 0
    for tag_id, tag, namespace, parts in split_candidates:
        if not dry_run:
            file_ids = [
                r[0]
                for r in con.execute(
                    "SELECT file_id FROM file_tags WHERE tag_id=?",
                    (tag_id,),
                )
            ]
            for part in parts:
                if not part:
                    continue

                existing = con.execute(
                    "SELECT id FROM tags WHERE tag=? AND namespace=?", (part, namespace or "")
                ).fetchone()
                if existing:
                    new_tag_id = existing[0]
                else:
                    con.execute(
                        "INSERT OR IGNORE INTO tags (tag, namespace) VALUES (?, ?)", (part, namespace or "")
                    )
                    row2 = con.execute(
                        "SELECT id FROM tags WHERE tag=? AND namespace=?", (part, namespace or "")
                    ).fetchone()
                    new_tag_id = row2[0]

                con.executemany(
                    "INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)",
                    ((fid, new_tag_id) for fid in file_ids),
                )

            con.execute("DELETE FROM file_tags WHERE tag_id=?", (tag_id,))
            con.execute("DELETE FROM tags WHERE id=?", (tag_id,))

        split_count += 1
        if split_count <= 20:
            logger.info(f"    Split '{tag}' -> {parts}")

    if split_count > 20:
        logger.info(f"    ... and {split_count - 20} more splits")

    return split_count
