"""Template write/update operations."""

import functools
import json
import logging
import sqlite3
import time
from collections.abc import Sequence

from .models_template_char_caption import extract_char_caption_texts
from .models_template_model_info import extract_model_from_prompt, extract_model_info

logger = logging.getLogger(__name__)

# When upsert_template alone takes longer than this, emit a per-substep
# dlog. Tuned to surface the slow path that dominates auto-import
# (1756ms / 1885ms observed = 93% of persist phase).
_UPSERT_TEMPLATE_SLOW_LOG_MS = 200.0


@functools.lru_cache(maxsize=512)
def _detect_prompt_lang_cached(raw_prompt: str) -> tuple:
    """Inner cached detector. Keyed on the exact prompt string.

    langdetect's natural-text extraction + n-gram analysis costs ~1.2s
    for a typical NAI v4 prompt (40 tags + caption). NAI/SD users
    typically iterate on the same prompt across many generates, so a
    process-wide LRU avoids re-running the analyzer for prompts we've
    already classified. The result is deterministic (langdetect uses a
    fixed DetectorFactory seed), so caching is safe.

    512 entries keeps memory bounded; LRU eviction handles the rare
    case of a user iterating through many distinct prompts.
    """
    try:
        from core.tools.lang_detect import detect_prompt_language
        result = detect_prompt_language(raw_prompt)
        return (result.lang, result.confidence)
    except Exception:
        return ("", 0.0)


def _detect_prompt_lang(raw_prompt: str | None) -> tuple:
    """Detect prompt language. Returns (lang, confidence)."""
    if not raw_prompt:
        return ("", 0.0)
    return _detect_prompt_lang_cached(raw_prompt)


def upsert_template(
    con: sqlite3.Connection,
    file_id: int,
    raw_prompt: str | None,
    raw_negative: str | None,
    fmt: str,
    raw_meta_json: str | None,
) -> int:
    _t_total = time.perf_counter()
    _steps: dict[str, float] = {}

    def _mark(name: str, t0: float) -> None:
        _steps[name] = round((time.perf_counter() - t0) * 1000, 1)

    _t = time.perf_counter()
    model_name, model_hash = extract_model_info(raw_meta_json, fmt)
    if model_name is None and raw_prompt:
        model_name, model_hash = extract_model_from_prompt(raw_prompt)
    _mark("extract_model", _t)

    # Prompt language detection
    _t = time.perf_counter()
    prompt_lang, prompt_lang_confidence = _detect_prompt_lang(raw_prompt)
    _mark("detect_lang", _t)

    _t = time.perf_counter()
    char_positive, char_negative = extract_char_caption_texts(raw_meta_json)
    _mark("extract_char_caption", _t)

    # Check if prompt_lang column exists (compatibility before migration 45)
    _t = time.perf_counter()
    has_lang_col = _has_column(con, "templates", "prompt_lang")
    has_char_cols = _has_column(con, "templates", "char_positive") and _has_column(con, "templates", "char_negative")
    _mark("has_column", _t)

    short_circuited = False
    if has_lang_col and has_char_cols:
        _t = time.perf_counter()
        existing = con.execute(
            """
            SELECT id, raw_prompt, raw_negative, format, raw_meta_json,
                   model_name, model_hash, prompt_lang, prompt_lang_confidence,
                   char_positive, char_negative
            FROM templates WHERE file_id=?
            """,
            (file_id,),
        ).fetchone()
        _mark("select_existing", _t)
        if existing is not None and (
            existing[1] == raw_prompt
            and existing[2] == raw_negative
            and existing[3] == fmt
            and existing[4] == raw_meta_json
            and existing[5] == model_name
            and existing[6] == model_hash
            and existing[7] == prompt_lang
            and existing[8] == prompt_lang_confidence
            and existing[9] == char_positive
            and existing[10] == char_negative
        ):
            short_circuited = True
            _emit_template_dlog(file_id, fmt, _steps, _t_total, short_circuited)
            return int(existing[0])
        _t = time.perf_counter()

        row = con.execute(
            """INSERT INTO templates(file_id, raw_prompt, raw_negative, format,
                   raw_meta_json, model_name, model_hash, prompt_lang, prompt_lang_confidence,
                   char_positive, char_negative)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(file_id) DO UPDATE SET
                   raw_prompt=excluded.raw_prompt,
                   raw_negative=excluded.raw_negative,
                   format=excluded.format,
                   raw_meta_json=excluded.raw_meta_json,
                   model_name=excluded.model_name,
                   model_hash=excluded.model_hash,
                   prompt_lang=excluded.prompt_lang,
                   prompt_lang_confidence=excluded.prompt_lang_confidence,
                   char_positive=excluded.char_positive,
                   char_negative=excluded.char_negative
               RETURNING id
            """,
            (file_id, raw_prompt, raw_negative, fmt, raw_meta_json,
             model_name, model_hash, prompt_lang, prompt_lang_confidence,
             char_positive, char_negative),
        ).fetchone()
        _mark("insert_or_update", _t)
    elif has_lang_col:
        _t = time.perf_counter()
        existing = con.execute(
            """
            SELECT id, raw_prompt, raw_negative, format, raw_meta_json,
                   model_name, model_hash, prompt_lang, prompt_lang_confidence
            FROM templates WHERE file_id=?
            """,
            (file_id,),
        ).fetchone()
        _mark("select_existing", _t)
        if existing is not None and (
            existing[1] == raw_prompt
            and existing[2] == raw_negative
            and existing[3] == fmt
            and existing[4] == raw_meta_json
            and existing[5] == model_name
            and existing[6] == model_hash
            and existing[7] == prompt_lang
            and existing[8] == prompt_lang_confidence
        ):
            short_circuited = True
            _emit_template_dlog(file_id, fmt, _steps, _t_total, short_circuited)
            return int(existing[0])

        _t = time.perf_counter()
        row = con.execute(
            """INSERT INTO templates(file_id, raw_prompt, raw_negative, format,
                   raw_meta_json, model_name, model_hash, prompt_lang, prompt_lang_confidence)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(file_id) DO UPDATE SET
                   raw_prompt=excluded.raw_prompt,
                   raw_negative=excluded.raw_negative,
                   format=excluded.format,
                   raw_meta_json=excluded.raw_meta_json,
                   model_name=excluded.model_name,
                   model_hash=excluded.model_hash,
                   prompt_lang=excluded.prompt_lang,
                   prompt_lang_confidence=excluded.prompt_lang_confidence
               RETURNING id
            """,
            (file_id, raw_prompt, raw_negative, fmt, raw_meta_json,
             model_name, model_hash, prompt_lang, prompt_lang_confidence),
        ).fetchone()
        _mark("insert_or_update", _t)
    else:
        _t = time.perf_counter()
        existing = con.execute(
            """
            SELECT id, raw_prompt, raw_negative, format, raw_meta_json,
                   model_name, model_hash
            FROM templates WHERE file_id=?
            """,
            (file_id,),
        ).fetchone()
        _mark("select_existing", _t)
        if existing is not None and (
            existing[1] == raw_prompt
            and existing[2] == raw_negative
            and existing[3] == fmt
            and existing[4] == raw_meta_json
            and existing[5] == model_name
            and existing[6] == model_hash
        ):
            short_circuited = True
            _emit_template_dlog(file_id, fmt, _steps, _t_total, short_circuited)
            return int(existing[0])

        _t = time.perf_counter()
        row = con.execute(
            """INSERT INTO templates(file_id, raw_prompt, raw_negative, format,
                   raw_meta_json, model_name, model_hash)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(file_id) DO UPDATE SET
                   raw_prompt=excluded.raw_prompt,
                   raw_negative=excluded.raw_negative,
                   format=excluded.format,
                   raw_meta_json=excluded.raw_meta_json,
                   model_name=excluded.model_name,
                   model_hash=excluded.model_hash
               RETURNING id
            """,
            (file_id, raw_prompt, raw_negative, fmt, raw_meta_json,
             model_name, model_hash),
        ).fetchone()
        _mark("insert_or_update", _t)
    _emit_template_dlog(file_id, fmt, _steps, _t_total, short_circuited)
    return int(row[0])


def _emit_template_dlog(
    file_id: int,
    fmt: str,
    steps: dict[str, float],
    t_start: float,
    short_circuited: bool,
) -> None:
    """Emit a per-step dlog if upsert_template took longer than the threshold."""
    total_ms = round((time.perf_counter() - t_start) * 1000, 1)
    if total_ms < _UPSERT_TEMPLATE_SLOW_LOG_MS:
        return
    from core.infra_core.debug_log import dlog
    dlog(
        "scan",
        "upsert_template.slow",
        file_id=file_id,
        fmt=fmt,
        short_circuited=short_circuited,
        total_ms=total_ms,
        **{f"{k}_ms": v for k, v in steps.items()},
    )


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Check whether a column exists in the table."""
    try:
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(c[1] == column for c in cols)
    except Exception:
        return False


def replace_template_tokens(con: sqlite3.Connection, template_id: int, tokens: Sequence) -> None:
    new_rows = [
        (t.token_type, json.dumps(t.payload, ensure_ascii=False), t.position)
        for t in tokens
    ]
    existing_rows = con.execute(
        "SELECT token_type, payload, position FROM template_tokens WHERE template_id=? ORDER BY position",
        (template_id,),
    )
    existing = [(r[0], r[1], r[2]) for r in existing_rows]
    if existing == new_rows:
        return

    con.execute("DELETE FROM template_tokens WHERE template_id=?", (template_id,))
    if new_rows:
        con.executemany(
            "INSERT INTO template_tokens(template_id, token_type, payload, position) VALUES(?,?,?,?)",
            [(template_id, token_type, payload, position) for token_type, payload, position in new_rows],
        )
