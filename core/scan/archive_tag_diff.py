"""Diff-based meta tag sync helpers for archive scanners."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence

from core.models_core.models_tags import insert_file_tags_batch, upsert_tag

TagRow = tuple[int, int, float, str]
_IN_CHUNK_SIZE = 500


def build_archive_meta_tag_rows(
    con: sqlite3.Connection,
    file_id: int,
    parsed_tags: Iterable[tuple],
    *,
    mtime: int,
) -> list[TagRow]:
    """Resolve parsed tags to file_tag rows with per-tag dedupe."""
    rows_map: dict[int, TagRow] = {}
    for ns, tag, weight in parsed_tags:
        tag_id = upsert_tag(con, ns, tag, first_seen_mtime=mtime)
        rows_map[int(tag_id)] = (int(file_id), int(tag_id), float(weight), "meta")
    return list(rows_map.values())


def _load_existing_meta_maps(
    con: sqlite3.Connection,
    file_ids: Sequence[int],
) -> dict[int, dict[int, float]]:
    existing_by_file: dict[int, dict[int, float]] = {}
    if not file_ids:
        return existing_by_file
    for i in range(0, len(file_ids), _IN_CHUNK_SIZE):
        chunk = [int(fid) for fid in file_ids[i : i + _IN_CHUNK_SIZE]]
        placeholders = ",".join("?" for _ in chunk)
        for row in con.execute(
            f"SELECT file_id, tag_id, weight FROM file_tags WHERE source='meta' AND file_id IN ({placeholders})",
            chunk,
        ):
            file_id = int(row[0])
            tag_id = int(row[1])
            weight = float(row[2])
            existing_by_file.setdefault(file_id, {})[tag_id] = weight
    return existing_by_file


def replace_archive_meta_tags_if_changed(
    con: sqlite3.Connection,
    file_id: int,
    rows: Sequence[TagRow],
) -> None:
    """Replace only when current meta tags differ."""
    replace_archive_meta_tags_batch_if_changed(con, {int(file_id): list(rows)})


def replace_archive_meta_tags_batch_if_changed(
    con: sqlite3.Connection,
    rows_by_file_id: dict[int, Sequence[TagRow]],
) -> None:
    """Batch diff-apply meta tags for multiple files."""
    if not rows_by_file_id:
        return
    file_ids = [int(fid) for fid in rows_by_file_id]
    existing_by_file = _load_existing_meta_maps(con, file_ids)

    rows_to_insert: list[TagRow] = []
    for file_id in file_ids:
        incoming_rows = list(rows_by_file_id.get(file_id) or [])
        incoming_map = {int(r[1]): float(r[2]) for r in incoming_rows}
        existing_map = existing_by_file.get(file_id, {})
        if incoming_map == existing_map:
            continue
        con.execute("DELETE FROM file_tags WHERE file_id=? AND source='meta'", (file_id,))
        if incoming_rows:
            rows_to_insert.extend(incoming_rows)

    if rows_to_insert:
        insert_file_tags_batch(con, rows_to_insert)
