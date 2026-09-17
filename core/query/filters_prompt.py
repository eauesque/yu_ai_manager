from typing import Any

from .fts_like_helpers import escape_like_param, trigram_match_phrase

_CHAR_NEGATIVE_JSON_LIKE = (
    "lower(COALESCE("
    "json_extract(json_extract(COALESCE(tm.raw_meta_json, '{}'), '$.Comment'), '$.v4_negative_prompt.caption.char_captions'), "
    "json_extract(COALESCE(tm.raw_meta_json, '{}'), '$.v4_negative_prompt.caption.char_captions'), "
    "''"
    ")) LIKE ?"
)
_CHAR_POSITIVE_JSON_LIKE = (
    "lower(COALESCE("
    "json_extract(json_extract(COALESCE(tm.raw_meta_json, '{}'), '$.Comment'), '$.v4_prompt.caption.char_captions'), "
    "json_extract(COALESCE(tm.raw_meta_json, '{}'), '$.v4_prompt.caption.char_captions'), "
    "''"
    ")) LIKE ?"
)


def apply_prompt_filters(
    where_parts: list[str],
    params: list[Any],
    in_prompt: str | None,
    in_negative: str | None,
    in_char_negative: str | None,
    in_char_positive: str | None,
    con=None,
) -> str:
    """Apply prompt / negative / char-prompt filters.

    Why MATCH instead of ``LIKE ? ESCAPE '\\'`` against templates_fts:
    SQLite (>= 3.43) silently disables the trigram-LIKE optimization
    whenever an ``ESCAPE`` clause is present (idxNum=0 full SCAN instead
    of L0/M0). ``column MATCH ?`` on a trigram FTS5 column hits idxNum=M0
    reliably. For terms too short for the trigram tokenizer (< 3 chars
    after stripping), fall back to a plain LIKE on the underlying
    templates table — full scan but unavoidable, and rare in practice.
    """
    join_fts = ""

    def _ensure_fts_join() -> None:
        nonlocal join_fts
        if not join_fts:
            join_fts = "JOIN templates_fts tf ON tf.rowid = tm.id"

    if in_prompt and in_prompt.strip():
        term = in_prompt.strip()
        phrase = trigram_match_phrase(term)
        if phrase is not None:
            _ensure_fts_join()
            where_parts.append("tf.raw_prompt MATCH ?")
            params.append(phrase)
        else:
            where_parts.append("tm.raw_prompt LIKE ? ESCAPE '\\'")
            params.append(f"%{escape_like_param(term)}%")

    if in_negative and in_negative.strip():
        term = in_negative.strip()
        phrase = trigram_match_phrase(term)
        if phrase is not None:
            _ensure_fts_join()
            where_parts.append("tf.raw_negative MATCH ?")
            params.append(phrase)
        else:
            where_parts.append("tm.raw_negative LIKE ? ESCAPE '\\'")
            params.append(f"%{escape_like_param(term)}%")

    if in_char_negative and in_char_negative.strip():
        term = in_char_negative.strip()
        if _templates_fts_has_char_column(con, "char_negative"):
            phrase = trigram_match_phrase(term)
            if phrase is not None:
                _ensure_fts_join()
                where_parts.append("tf.char_negative MATCH ?")
                params.append(phrase)
            else:
                # Term too short for trigram; fall back to the json path
                # (semantically correct for char-prompt search).
                where_parts.append(_CHAR_NEGATIVE_JSON_LIKE)
                params.append(f"%{term.lower()}%")
        else:
            where_parts.append(_CHAR_NEGATIVE_JSON_LIKE)
            params.append(f"%{term.lower()}%")

    if in_char_positive and in_char_positive.strip():
        term = in_char_positive.strip()
        if _templates_fts_has_char_column(con, "char_positive"):
            phrase = trigram_match_phrase(term)
            if phrase is not None:
                _ensure_fts_join()
                where_parts.append("tf.char_positive MATCH ?")
                params.append(phrase)
            else:
                where_parts.append(_CHAR_POSITIVE_JSON_LIKE)
                params.append(f"%{term.lower()}%")
        else:
            where_parts.append(_CHAR_POSITIVE_JSON_LIKE)
            params.append(f"%{term.lower()}%")

    return join_fts


def _templates_fts_has_char_column(con, column_name: str) -> bool:
    if con is None:
        return False
    try:
        rows = con.execute("PRAGMA table_info(templates_fts)").fetchall()
        return any(row[1] == column_name for row in rows)
    except Exception:
        return False
