import contextlib
import json
import logging
import sqlite3
import time

from core.event_bus import emit
from core.event_bus.event_types import ANALYSIS_COMPLETE
from core.utils.zstd_blob import compress_text, decompress_blob

from .engines import AnalysisResult

logger = logging.getLogger(__name__)


def ensure_analysis_table(con: sqlite3.Connection):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            engine TEXT NOT NULL,
            analyzed_at INTEGER NOT NULL,
            tags_json TEXT,
            quality_score REAL,
            quality_notes BLOB,
            description TEXT,
            style TEXT,
            composition TEXT,
            mood TEXT,
            color_palette_json TEXT,
            prompt_suggestion BLOB,
            raw_response BLOB,
            FOREIGN KEY (file_id) REFERENCES files(id),
            UNIQUE(file_id, engine)
        )
    """
    )
    con.commit()


_SAVE_RETRIES = 8
_SAVE_RETRY_DELAY = 1.0  # seconds
_ANALYSIS_COLUMNS = (
    "file_id, engine, analyzed_at, tags_json, quality_score, quality_notes, description, "
    "style, composition, mood, color_palette_json, prompt_suggestion"
)

_UPSERT_SQL = """
    INSERT INTO analysis (file_id, engine, analyzed_at, tags_json, quality_score,
                          quality_notes, description, style, composition, mood,
                          color_palette_json, prompt_suggestion, raw_response)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(file_id, engine) DO UPDATE SET
        analyzed_at=excluded.analyzed_at,
        tags_json=excluded.tags_json,
        quality_score=excluded.quality_score,
        quality_notes=excluded.quality_notes,
        description=excluded.description,
        style=excluded.style,
        composition=excluded.composition,
        mood=excluded.mood,
        color_palette_json=excluded.color_palette_json,
        prompt_suggestion=excluded.prompt_suggestion,
        raw_response=excluded.raw_response
"""


def _analysis_params(file_id: int, engine_name: str, result: AnalysisResult) -> tuple:
    return (
        file_id,
        engine_name,
        int(time.time()),
        json.dumps(result.tags, ensure_ascii=False),
        result.quality_score,
        compress_text(result.quality_notes),
        result.description,
        result.style,
        result.composition,
        result.mood,
        json.dumps(result.color_palette, ensure_ascii=False),
        compress_text(result.prompt_suggestion),
        compress_text(result.raw_response),
    )


def save_analysis(
    con: sqlite3.Connection,
    file_id: int,
    engine_name: str,
    result: AnalysisResult,
    *,
    auto_commit: bool = True,
    emit_event: bool = True,
):
    """Save analysis results to the DB.

    Falls back to a fresh dedicated connection on retry,
    in case the passed connection causes lock contention after a long period.
    """
    params = _analysis_params(file_id, engine_name, result)
    current_con = con
    try:
        for attempt in range(_SAVE_RETRIES):
            try:
                current_con.execute(_UPSERT_SQL, params)
                if auto_commit:
                    current_con.commit()
                if emit_event:
                    emit(ANALYSIS_COMPLETE, {"file_id": file_id, "engine": engine_name})
                return
            except Exception as e:
                if "locked" in str(e) and attempt < _SAVE_RETRIES - 1:
                    time.sleep(_SAVE_RETRY_DELAY * (attempt + 1))
                    # Retry with new connection from 3rd attempt onward.
                    # Keep this only for auto-commit mode to avoid mixing
                    # caller-managed transactions with a fallback connection.
                    if auto_commit and attempt >= 2 and current_con is con:
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
    finally:
        if current_con is not con:
            current_con.close()


def save_analysis_batch(
    con: sqlite3.Connection,
    items: list[tuple[int, str, AnalysisResult]],
    *,
    emit_events: bool = True,
) -> int:
    """Save multiple analysis results with one transaction/commit."""
    if not items:
        return 0

    for attempt in range(_SAVE_RETRIES):
        try:
            for file_id, engine_name, result in items:
                con.execute(_UPSERT_SQL, _analysis_params(file_id, engine_name, result))
            con.commit()
            if emit_events:
                for file_id, engine_name, _ in items:
                    emit(ANALYSIS_COMPLETE, {"file_id": file_id, "engine": engine_name})
            return len(items)
        except Exception as e:
            with contextlib.suppress(Exception):
                con.rollback()
            if "locked" in str(e) and attempt < _SAVE_RETRIES - 1:
                time.sleep(_SAVE_RETRY_DELAY * (attempt + 1))
                continue
            raise

    return 0


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "file_id": row["file_id"],
        "engine": row["engine"],
        "analyzed_at": row["analyzed_at"],
        "tags": json.loads(row["tags_json"] or "[]"),
        "quality_score": row["quality_score"],
        "quality_notes": decompress_blob(row["quality_notes"]),
        "description": row["description"] or "",
        "style": row["style"],
        "composition": row["composition"],
        "mood": row["mood"],
        "color_palette": json.loads(row["color_palette_json"] or "[]"),
        "prompt_suggestion": decompress_blob(row["prompt_suggestion"]),
        # raw_response is intentionally excluded (regenerable debug field).
        # If added later, wrap with decompress_blob().
    }


def _fetch_analysis_row(con: sqlite3.Connection, file_id: int, engine: str | None = None) -> sqlite3.Row | None:
    if engine:
        return con.execute(
            f"SELECT {_ANALYSIS_COLUMNS} FROM analysis WHERE file_id=? AND engine=?",
            (file_id, engine),
        ).fetchone()
    return con.execute(
        f"SELECT {_ANALYSIS_COLUMNS} FROM analysis WHERE file_id=? ORDER BY analyzed_at DESC LIMIT 1",
        (file_id,),
    ).fetchone()


def get_analysis(con: sqlite3.Connection, file_id: int, engine: str | None = None) -> dict | None:
    row = _fetch_analysis_row(con, file_id, engine)
    if not row:
        return None
    return _row_to_dict(row)


def get_all_analyses(con: sqlite3.Connection, file_id: int) -> list:
    """Get all analysis results for a file (newest first)."""
    rows = con.execute(
        f"SELECT {_ANALYSIS_COLUMNS} FROM analysis WHERE file_id=? ORDER BY analyzed_at DESC, engine ASC",
        (file_id,),
    )
    return [_row_to_dict(r) for r in rows]
