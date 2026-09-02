"""Schema migration 52: materialized character-caption columns + FTS rebuild."""

import contextlib
import logging
import sqlite3
import time

from core.models_core.models_template_char_caption import extract_char_caption_texts
from core.services_core.db_api import set_startup_status

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)

_BACKFILL_WHERE = """
    FROM templates t
    JOIN files f ON f.id = t.file_id
    WHERE (
        f.meta_source IN ('novelai_v4_png', 'novelai_v4_webp')
        OR COALESCE(t.raw_meta_json, '') LIKE '%v4_prompt%'
        OR COALESCE(t.raw_meta_json, '') LIKE '%char_captions%'
        OR COALESCE(t.char_positive, '') != ''
        OR COALESCE(t.char_negative, '') != ''
    )
"""


def _iter_backfill_rows(cur: sqlite3.Cursor, batch_size: int = 1000):
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            return
        yield rows


def apply_migration_52(con: sqlite3.Connection) -> None:
    """Add char caption columns to templates and rebuild templates_fts."""
    logger.info("  -> Migration 52: character caption columns + FTS rebuild")
    t0 = time.perf_counter()

    for col in ("char_positive", "char_negative"):
        with contextlib.suppress(Exception):
            con.execute(f"ALTER TABLE templates ADD COLUMN {col} TEXT DEFAULT ''")

    # Existing templates FTS will be rebuilt anyway, so keep its triggers out of the
    # backfill path to avoid 25k+ pointless delete/insert churn during UPDATEs.
    con.execute("DROP TRIGGER IF EXISTS templates_ai")
    con.execute("DROP TRIGGER IF EXISTS templates_ad")
    con.execute("DROP TRIGGER IF EXISTS templates_au")

    total_candidates = con.execute(
        f"SELECT COUNT(*) {_BACKFILL_WHERE}"
    ).fetchone()[0]
    logger.info("  -> Migration 52 backfill target rows: %s", total_candidates)
    set_startup_status({
        "kind": "migration",
        "stage": "backfill",
        "step": 52,
        "total_rows": total_candidates,
    })

    t_scan0 = time.perf_counter()
    cur = con.execute(
        f"""
        SELECT
            t.id,
            t.raw_meta_json,
            COALESCE(t.char_positive, ''),
            COALESCE(t.char_negative, '')
        {_BACKFILL_WHERE}
        """
    )
    scan_ms = round((time.perf_counter() - t_scan0) * 1000)

    t_extract0 = time.perf_counter()
    scanned_rows = 0
    updated_rows = 0
    next_progress_log = 5000
    for rows in _iter_backfill_rows(cur):
        updates = []
        for tid, raw_meta_json, existing_positive, existing_negative in rows:
            scanned_rows += 1
            char_positive, char_negative = extract_char_caption_texts(raw_meta_json)
            if char_positive != (existing_positive or "") or char_negative != (existing_negative or ""):
                updates.append((char_positive, char_negative, tid))
        if updates:
            con.executemany(
                "UPDATE templates SET char_positive=?, char_negative=? WHERE id=?",
                updates,
            )
            updated_rows += len(updates)
        if scanned_rows >= next_progress_log or scanned_rows == total_candidates:
            set_startup_status({
                "kind": "migration",
                "stage": "backfill",
                "step": 52,
                "total_rows": total_candidates,
                "processed_rows": scanned_rows,
                "updated_rows": updated_rows,
            })
            logger.info(
                "  -> Migration 52 backfill progress: %s/%s rows (%s updated)",
                scanned_rows,
                total_candidates,
                updated_rows,
            )
            next_progress_log += 5000
    extract_update_ms = round((time.perf_counter() - t_extract0) * 1000)

    logger.info("  -> Migration 52 rebuilding templates_fts")
    set_startup_status({
        "kind": "migration",
        "stage": "rebuild_fts",
        "step": 52,
        "total_rows": total_candidates,
        "processed_rows": scanned_rows,
        "updated_rows": updated_rows,
    })
    con.execute("DROP TABLE IF EXISTS templates_fts")

    con.execute(
        """
        CREATE VIRTUAL TABLE templates_fts
        USING fts5(
            raw_prompt,
            raw_negative,
            char_positive,
            char_negative,
            content='templates',
            content_rowid='id',
            tokenize="unicode61 tokenchars '_:.'"
        )
        """
    )

    con.execute(
        """
        CREATE TRIGGER templates_ai AFTER INSERT ON templates BEGIN
            INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
            VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
        END
        """
    )
    con.execute(
        """
        CREATE TRIGGER templates_ad AFTER DELETE ON templates BEGIN
            INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
            VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
        END
        """
    )
    con.execute(
        """
        CREATE TRIGGER templates_au AFTER UPDATE ON templates BEGIN
            INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative, char_positive, char_negative)
            VALUES ('delete', old.id, old.raw_prompt, old.raw_negative, old.char_positive, old.char_negative);
            INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
            VALUES (new.id, new.raw_prompt, new.raw_negative, new.char_positive, new.char_negative);
        END
        """
    )

    t_rebuild0 = time.perf_counter()
    con.execute("INSERT INTO templates_fts(templates_fts) VALUES('rebuild')")
    rebuild_ms = round((time.perf_counter() - t_rebuild0) * 1000)
    total_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "  -> Migration 52 timing: scan=%sms extract_update=%sms rebuild=%sms total=%sms rows=%s updated=%s",
        scan_ms,
        extract_update_ms,
        rebuild_ms,
        total_ms,
        scanned_rows,
        updated_rows,
    )
    set_schema_version(con, 52, "character caption columns + templates_fts rebuild")
