"""LIKE-based query helpers for trigram FTS5 tables.

The project migrated ``files_path_fts`` and ``templates_fts`` to the
``trigram`` tokenizer in v4.119.33 (migration 64) for CJK support. With
trigram, the previous ``MATCH '"foo"*'`` syntax no longer matches anything
because trigram tokens are exactly 3 characters; a 4+ char prefix has no
indexed token to match. SQLite's FTS5 trigram tokenizer is documented to
accelerate ``LIKE '%substring%'`` instead, so all FTS substring queries are
expressed in that form.

These helpers centralise the LIKE escape rules so call sites don't
re-implement them.
"""

from __future__ import annotations


def escape_like_param(text: str) -> str:
    """Escape SQL LIKE wildcards in *text* using a backslash escape character.

    Pair with ``LIKE ? ESCAPE '\\'`` in the SQL.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_substring(text: str) -> str:
    """Return ``%escaped_text%`` ready to bind into ``LIKE ? ESCAPE '\\'``.

    NOTE: SQLite (>= 3.43) does NOT apply the trigram LIKE optimization when the
    ``ESCAPE`` clause is present — the FTS5 virtual table falls through to a
    full SCAN (idxNum=0) instead of the trigram-accelerated path
    (idxNum=L0). Whenever you can, prefer ``path_fts_match_phrase`` and a
    ``... MATCH ?`` predicate against ``files_path_fts`` / ``templates_fts``.
    """
    return f"%{escape_like_param(text)}%"


def trigram_match_phrase(text: str) -> str | None:
    """Return an FTS5 MATCH phrase parameter (e.g. ``'"arn-75w"'``) for trigram
    substring search. Works for any column on a trigram-tokenized FTS5 table
    (``files_path_fts``, ``templates_fts``). Returns ``None`` when *text* is
    too short (< 3 chars after stripping) for the trigram tokenizer to index
    it — callers should skip the FTS subquery in that case rather than fall
    through to a LIKE-with-ESCAPE full scan.
    """
    cleaned = (text or "").strip()
    if len(cleaned) < 3:
        return None
    # Wrap as a phrase. Escape FTS5 phrase metacharacter (double-quote) by
    # doubling. Other characters (including %, _, /, \, hyphen, etc.) are
    # plain text inside an FTS5 phrase.
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


# Backward-compat alias: existing callers use the path-prefixed name.
path_fts_match_phrase = trigram_match_phrase
