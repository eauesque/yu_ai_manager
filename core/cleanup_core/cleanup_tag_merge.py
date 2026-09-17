"""Tag cleanup/merge database operations."""

import sqlite3

from .cleanup_tag_merge_phase import cleanup_orphan_tags, run_merge_phase
from .cleanup_tag_split_phase import run_split_phase


def cleanup_normalize_tags(con: sqlite3.Connection, dry_run: bool = False) -> int:
    run_split_phase(con, dry_run=dry_run)
    merge_count = run_merge_phase(con, dry_run=dry_run)

    if not dry_run:
        cleanup_orphan_tags(con)
        con.commit()

    return merge_count
