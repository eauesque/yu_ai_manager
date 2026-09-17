"""DB persistence of OCR results."""

from __future__ import annotations

import json
import logging
import sqlite3
import time

from core.event_bus import emit as _emit_event
from core.event_bus.event_types import OCR_COMPLETE

from .types import OcrRegion, OcrResult

logger = logging.getLogger(__name__)

_SAVE_RETRIES = 8
_SAVE_RETRY_DELAY = 1.0
_OCR_RESULT_COLUMNS = (
    "id, file_id, engine, task, regions_json, full_text, structured_json, language, created_at"
)


def ensure_ocr_tables(con: sqlite3.Connection) -> None:
    """Create OCR tables if they do not exist (fallback)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS file_ocr_results (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            engine TEXT NOT NULL,
            task TEXT NOT NULL DEFAULT 'ocr',
            regions_json TEXT,
            full_text TEXT,
            structured_json TEXT,
            language TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, engine, task)
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_ocr_file_id
        ON file_ocr_results(file_id)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_ocr_task
        ON file_ocr_results(task)
    """)
    con.commit()


def save_ocr_result(con: sqlite3.Connection, result: OcrResult) -> int:
    """Save OCR results to DB. Returns row id."""
    regions_json = json.dumps(
        [r.to_dict() for r in result.regions], ensure_ascii=False
    )
    structured = {}
    if result.task == "ocr_document":
        structured = {
            "headings": result.headings,
            "tables": result.tables,
            "page_layout": result.page_layout,
        }
    structured_json = json.dumps(structured, ensure_ascii=False) if structured else None

    params = (
        result.file_id,
        result.engine,
        result.task,
        regions_json,
        result.full_text,
        structured_json,
        result.language,
        int(time.time()),
    )
    sql = """
        INSERT INTO file_ocr_results
            (file_id, engine, task, regions_json, full_text,
             structured_json, language, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id, engine, task) DO UPDATE SET
            regions_json=excluded.regions_json,
            full_text=excluded.full_text,
            structured_json=excluded.structured_json,
            language=excluded.language,
            created_at=excluded.created_at
    """
    current_con = con
    for attempt in range(_SAVE_RETRIES):
        try:
            cur = current_con.execute(sql, params)
            current_con.commit()
            _emit_event(OCR_COMPLETE, {
                "file_id": result.file_id, "engine": result.engine, "task": result.task,
            })
            return cur.lastrowid
        except Exception as e:
            if "locked" in str(e) and attempt < _SAVE_RETRIES - 1:
                time.sleep(_SAVE_RETRY_DELAY * (attempt + 1))
                if attempt >= 2 and current_con is con:
                    try:
                        from core.services_core.db_cipher import apply_key
                        from core.services_core.db_cipher import sqlite3 as _sc
                        from core.services_core.db_state import get_db_path
                        fresh = _sc.connect(str(get_db_path()), timeout=30)
                        apply_key(fresh)
                        fresh.row_factory = _sc.Row
                        current_con = fresh
                    except Exception:
                        logger.warning("could not open a fresh DB connection; reusing the caller's", exc_info=True)
                continue
            raise
    return 0


def _row_to_result(row: sqlite3.Row) -> dict:
    """Convert a DB row to dict."""
    regions = json.loads(row["regions_json"] or "[]")
    structured = json.loads(row["structured_json"] or "{}")
    return {
        "id": row["id"],
        "file_id": row["file_id"],
        "engine": row["engine"],
        "task": row["task"],
        "regions": regions,
        "full_text": row["full_text"] or "",
        "language": row["language"] or "",
        "headings": structured.get("headings", []),
        "tables": structured.get("tables", []),
        "page_layout": structured.get("page_layout", ""),
        "created_at": row["created_at"],
    }


def _row_to_ocr_result(row: sqlite3.Row) -> OcrResult:
    """Convert a DB row to an OcrResult object."""
    d = _row_to_result(row)
    regions = [
        OcrRegion(
            region_id=r.get("region_id", i),
            bbox=r.get("bbox", []),
            text=r.get("text", ""),
            confidence=r.get("confidence", 0.0),
            direction=r.get("direction", "horizontal"),
            label=r.get("label", ""),
        )
        for i, r in enumerate(d["regions"])
    ]
    return OcrResult(
        id=d["id"],
        file_id=d["file_id"],
        engine=d["engine"],
        task=d["task"],
        regions=regions,
        full_text=d["full_text"],
        language=d["language"],
        headings=d["headings"],
        tables=d["tables"],
        page_layout=d["page_layout"],
    )


def _fetch_latest_ocr_row(
    con: sqlite3.Connection,
    file_id: int,
    *,
    task: str = "",
    engine: str = "",
) -> sqlite3.Row | None:
    if task and engine:
        return con.execute(
            f"SELECT {_OCR_RESULT_COLUMNS} FROM file_ocr_results "
            "WHERE file_id=? AND task=? AND engine=?",
            (file_id, task, engine),
        ).fetchone()
    if task:
        return con.execute(
            f"SELECT {_OCR_RESULT_COLUMNS} FROM file_ocr_results "
            "WHERE file_id=? AND task=? ORDER BY created_at DESC LIMIT 1",
            (file_id, task),
        ).fetchone()
    return con.execute(
        f"SELECT {_OCR_RESULT_COLUMNS} FROM file_ocr_results "
        "WHERE file_id=? ORDER BY created_at DESC LIMIT 1",
        (file_id,),
    ).fetchone()


def get_ocr_result(
    con: sqlite3.Connection, file_id: int,
    task: str = "", engine: str = "",
) -> dict | None:
    """Get OCR results."""
    try:
        row = _fetch_latest_ocr_row(con, file_id, task=task, engine=engine)
    except Exception:
        return None
    if not row:
        return None
    return _row_to_result(row)


def get_ocr_result_obj(
    con: sqlite3.Connection, file_id: int,
    task: str = "", engine: str = "",
) -> OcrResult | None:
    """Get OCR results as OcrResult objects."""
    try:
        row = _fetch_latest_ocr_row(con, file_id, task=task, engine=engine)
    except Exception:
        return None
    if not row:
        return None
    return _row_to_ocr_result(row)


def get_all_ocr_results(con: sqlite3.Connection, file_id: int) -> list[dict]:
    """Get all OCR results for the same file."""
    try:
        rows = con.execute(
            f"SELECT {_OCR_RESULT_COLUMNS} FROM file_ocr_results "
            "WHERE file_id=? ORDER BY created_at DESC",
            (file_id,),
        ).fetchall()
    except Exception:
        return []
    return [_row_to_result(r) for r in rows]


def delete_ocr_result(
    con: sqlite3.Connection, file_id: int,
    task: str = "", engine: str = "",
) -> int:
    """Delete OCR results. Returns delete count."""
    try:
        if task and engine:
            cur = con.execute(
                "DELETE FROM file_ocr_results WHERE file_id=? AND task=? AND engine=?",
                (file_id, task, engine),
            )
        elif task:
            cur = con.execute(
                "DELETE FROM file_ocr_results WHERE file_id=? AND task=?",
                (file_id, task),
            )
        else:
            cur = con.execute(
                "DELETE FROM file_ocr_results WHERE file_id=?",
                (file_id,),
            )
    except Exception:
        return 0
    con.commit()
    return cur.rowcount
