"""Shared helpers for archive hash backfill updates."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence


def apply_hash_backfill_updates(
    con: sqlite3.Connection,
    updates: Sequence[tuple[int, int, str]],
) -> list[tuple[int, int]]:
    """Apply conditional hash updates and return actually-updated entries.

    updates: [(idx, file_id, content_hash), ...]
    return:  [(idx, file_id), ...] for rows that were updated.
    """
    changed: list[tuple[int, int]] = []
    for idx, file_id, content_hash in updates:
        cur = con.execute(
            "UPDATE files SET hash=? WHERE id=? AND hash IS NOT ?",
            (str(content_hash), int(file_id), str(content_hash)),
        )
        if cur.rowcount:
            changed.append((int(idx), int(file_id)))
    return changed
