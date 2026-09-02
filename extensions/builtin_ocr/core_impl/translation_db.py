"""DB persistence layer for translation results.

Manages the file_translations table: create, save, query.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .translation import TranslationResult

_TRANSLATION_COLUMNS = (
    "id, ocr_result_id, target_lang, translated_text, region_translations_json, engine, created_at"
)


def ensure_translation_table(con) -> None:
    """Create file_translations table if it does not exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS file_translations (
            id INTEGER PRIMARY KEY,
            ocr_result_id INTEGER NOT NULL,
            target_lang TEXT NOT NULL,
            translated_text TEXT,
            region_translations_json TEXT,
            engine TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (ocr_result_id) REFERENCES file_ocr_results(id),
            UNIQUE(ocr_result_id, target_lang)
        )
    """)


def save_translation(
    con, ocr_result_id: int, result: TranslationResult,
) -> int:
    """Save translation result to DB (upsert)."""
    sql = """
        INSERT INTO file_translations
            (ocr_result_id, target_lang, translated_text,
             region_translations_json, engine, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ocr_result_id, target_lang) DO UPDATE SET
            translated_text=excluded.translated_text,
            region_translations_json=excluded.region_translations_json,
            engine=excluded.engine,
            created_at=excluded.created_at
    """
    region_json = json.dumps(
        result.region_translations, ensure_ascii=False,
    ) if result.region_translations else None

    cur = con.execute(sql, (
        ocr_result_id,
        result.target_lang,
        result.translated_text,
        region_json,
        result.engine,
        int(time.time()),
    ))
    con.commit()
    return cur.lastrowid


def get_translation(
    con, ocr_result_id: int, target_lang: str = "",
) -> dict | None:
    """Retrieve a translation result by ocr_result_id (and optionally target_lang)."""
    try:
        if target_lang:
            row = con.execute(
                f"SELECT {_TRANSLATION_COLUMNS} FROM file_translations "
                "WHERE ocr_result_id=? AND target_lang=?",
                (ocr_result_id, target_lang),
            ).fetchone()
        else:
            row = con.execute(
                f"SELECT {_TRANSLATION_COLUMNS} FROM file_translations WHERE ocr_result_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (ocr_result_id,),
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return _translation_row_to_dict(row)


def get_translations_for_file(con, file_id: int) -> list[dict]:
    """Retrieve all translation results for a given file."""
    try:
        rows = con.execute("""
            SELECT
                t.id,
                t.ocr_result_id,
                t.target_lang,
                t.translated_text,
                t.region_translations_json,
                t.engine,
                t.created_at,
                o.file_id,
                o.task,
                o.engine as ocr_engine
            FROM file_translations t
            JOIN file_ocr_results o ON o.id = t.ocr_result_id
            WHERE o.file_id = ?
            ORDER BY t.created_at DESC
        """, (file_id,)).fetchall()
    except Exception:
        return []
    return [_translation_row_to_dict(r) for r in rows]


def _translation_row_to_dict(row) -> dict:
    """Convert a DB row to a plain dict."""
    d = {
        "id": row["id"],
        "ocr_result_id": row["ocr_result_id"],
        "target_lang": row["target_lang"],
        "translated_text": row["translated_text"],
        "engine": row["engine"],
        "created_at": row["created_at"],
    }
    region_json = row["region_translations_json"]
    if region_json:
        try:
            d["region_translations"] = json.loads(region_json)
        except json.JSONDecodeError:
            d["region_translations"] = []
    else:
        d["region_translations"] = []
    # Fields from JOIN result (if present). sqlite3.Row's __contains__ checks
    # values, not keys, so we must inspect row.keys() explicitly.
    row_keys = row.keys() if hasattr(row, "keys") else ()
    for key in ("file_id", "task", "ocr_engine"):
        if key in row_keys:
            d[key] = row[key]
    return d
