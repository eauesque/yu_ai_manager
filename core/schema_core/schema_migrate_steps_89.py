"""Migration 89: normalize `files.path` for rows written before v4.711.1.

Before v4.711.1, the Rust native bridge-import tier (`sweep_common.rs::
native_import_one_with` / `bare_upsert_one`, used by NAI/SD/ComfyUI bridge
auto-import, `scan_native.rs`, and `watcher.rs`) wrote `files.path` verbatim,
while Python's `scanner_regular.py` always ran `normalize_path()` (abspath +
normpath, plus `normcase` on Windows) first. A `save_folder` config value
spelled with forward vs backslashes (e.g. `h:/img` vs `h:\\img`) could
therefore produce two `files` rows for the same on-disk file: one written by
Python in normalized form, one written by Rust verbatim.

v4.711.1 made the Rust tier normalize going forward, but existing rows
written before that fix are untouched by code changes alone -- this
migration is the one-time data repair. See TODO.md v4.708.2 and the
v4.711.1 CHANGELOG entry.

Zip-member rows (`is_zip_member=1`) are skipped: their `path` is an
archive-internal virtual path, not a real filesystem path, so running it
through `normalize_path()` (which calls `os.path.abspath`) would corrupt it.
Already-deleted rows (`is_deleted=1`) are also skipped -- they are inert
(excluded from search) and skipping them keeps a re-run of this migration a
no-op.

Rows that collide after normalization are resolved by DELETING the loser
row outright (`file_translations`/`file_ocr_results`/`templates`/`file_tags`
first, then `files`) rather than soft-deleting it under a renamed path -- a
soft-deleted row with a mangled path is unreachable by any scan/search/cleanup
path, which just relocates the "duplicate metadata" problem instead of
solving it. `file_ocr_results`/`file_translations` have no `ON DELETE CASCADE`
(unlike every other file_id-referencing table -- see the DELETE
/api/ocr/result/{file_id} endpoint, which does the same two-stage cleanup),
so they must be deleted explicitly or `DELETE FROM files` raises a foreign
key violation for a loser row that has OCR data. This mirrors
`core/cleanup_core/cleanup_files.py::cleanup_dedupe_paths`, the project's
existing tool for resolving `files.path` duplicates.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from core.platform.path_normalize import normalize_path

from .schema_connect import table_has_column
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _pick_winner(rows: list[tuple[int, int, int]]) -> int:
    """Pick which row id in a normalization-collision group survives.

    `rows` items are `(file_id, parser_version, mtime)` -- all rows entering
    this are already filtered to `is_deleted=0`. Preference: higher
    parser_version (more fully processed), then newer mtime, then lowest id
    (oldest registration) as a stable tiebreaker.
    """
    return min(
        rows,
        key=lambda r: (-r[1], -r[2], r[0]),
    )[0]


def apply_migration_89(con: sqlite3.Connection) -> None:
    logger.info("  -> Migration 89: normalize files.path (pre-v4.711.1 Rust rows)")

    # Guard for schemas older than the columns this migration reads/writes
    # (e.g. a minimal test fixture seeded at v80 replaying every migration
    # up to CURRENT_SCHEMA_VERSION). Every real database at this point in
    # history already has all three -- this is a no-op there.
    required_cols = ("is_zip_member", "is_deleted", "parser_version", "mtime")
    if not all(table_has_column(con, "files", col) for col in required_cols):
        logger.info("Migration 89: files table missing required columns, skipping")
        set_schema_version(con, 89, "normalize files.path (bridge Rust import parity)")
        return

    rows = con.execute(
        "SELECT id, path, COALESCE(parser_version, 1), mtime "
        "FROM files WHERE is_zip_member = 0 AND is_deleted = 0"
    ).fetchall()

    groups: dict[str, list[tuple[int, str, int, int]]] = {}
    for file_id, path, parser_version, mtime in rows:
        norm = normalize_path(Path(path))
        groups.setdefault(norm, []).append((file_id, path, parser_version, mtime))

    # file_ocr_results has no ON DELETE CASCADE to files (see module
    # docstring); table_has_column returns False for a nonexistent table,
    # so this also no-ops cleanly against a minimal test fixture that
    # doesn't define it.
    has_ocr_tables = table_has_column(con, "file_ocr_results", "file_id")
    renamed = 0
    removed = 0
    for norm, group in groups.items():
        if len(group) == 1:
            file_id, path, *_ = group[0]
            if path != norm:
                con.execute("UPDATE files SET path=? WHERE id=?", (norm, file_id))
                renamed += 1
            continue

        # Collision: distinct live rows normalize to the same path (the bug
        # this migration repairs). Keep the more complete row and rewrite its
        # path to the normalized form; delete the rest outright -- their
        # metadata (templates/file_tags; other file_id-referencing tables
        # cascade via their own ON DELETE CASCADE FKs) is discarded rather
        # than orphaned, same as cleanup_dedupe_paths does for the general
        # duplicate-path case. file_ocr_results/file_translations have no
        # cascade (see the module docstring), so they need explicit cleanup
        # before the files row can be deleted without a FK violation.
        winner = _pick_winner([(r[0], r[2], r[3]) for r in group])
        winner_original_path = next(r[1] for r in group if r[0] == winner)
        for row in group:
            file_id = row[0]
            if file_id != winner:
                if has_ocr_tables:
                    con.execute(
                        "DELETE FROM file_translations WHERE ocr_result_id IN "
                        "(SELECT id FROM file_ocr_results WHERE file_id=?)",
                        (file_id,),
                    )
                    con.execute("DELETE FROM file_ocr_results WHERE file_id=?", (file_id,))
                con.execute("DELETE FROM templates WHERE file_id=?", (file_id,))
                con.execute("DELETE FROM file_tags WHERE file_id=?", (file_id,))
                con.execute("DELETE FROM files WHERE id=?", (file_id,))
                removed += 1
        if winner_original_path != norm:
            con.execute("UPDATE files SET path=? WHERE id=?", (norm, winner))
            renamed += 1

    logger.info(
        "Migration 89: normalized %d path(s), removed %d duplicate row(s)",
        renamed,
        removed,
    )
    set_schema_version(con, 89, "normalize files.path (bridge Rust import parity)")

