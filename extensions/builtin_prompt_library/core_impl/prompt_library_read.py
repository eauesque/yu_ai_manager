"""Prompt Library read operations: list, get, search."""

from __future__ import annotations

import json
from typing import Any

from .prompt_library_db import get_pl_read_db

_COLUMNS = (
    "id", "title", "positive", "negative", "seed", "steps",
    "sampler", "cfg_scale", "model_name", "memo",
    "source_file_id", "characters_json", "created_at", "updated_at",
)


def _fts5_phrase(q: str) -> str:
    """Wrap user text as an FTS5 double-quoted phrase to avoid syntax errors.

    FTS5 treats ``"..."`` as a phrase query, so any special tokens inside
    (bare ``*``, ``NEAR(``, lone ``"`` etc.) are interpreted literally instead
    of raising an OperationalError.
    """
    return '"' + q.replace('"', '""') + '"'


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(zip(_COLUMNS, row, strict=False))
    raw = d.pop("characters_json", "") or ""
    if raw:
        try:
            d["characters"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d["characters"] = []
    else:
        d["characters"] = []
    return d


def list_prompts(
    *,
    q: str | None = None,
    folder_id: int | None = None,
    tag_id: int | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Return paginated prompt list with total count.

    Returns {"items": [...], "total": int}.
    """
    allowed_sort = {"updated_at", "created_at", "title"}
    if sort not in allowed_sort:
        sort = "updated_at"
    if order.lower() not in ("asc", "desc"):
        order = "desc"

    con = get_pl_read_db()
    base = "FROM prompt_library p"
    wheres: list[str] = []
    params: list[Any] = []

    if folder_id is not None:
        base += " JOIN prompt_library_folder_items fi ON fi.prompt_id=p.id"
        wheres.append("fi.folder_id=?")
        params.append(folder_id)

    if tag_id is not None:
        base += " JOIN prompt_library_tag_map tm ON tm.prompt_id=p.id"
        wheres.append("tm.tag_id=?")
        params.append(tag_id)

    if q:
        wheres.append(
            "p.id IN (SELECT rowid FROM prompt_library_fts WHERE prompt_library_fts MATCH ?)"
        )
        params.append(_fts5_phrase(q))

    where_clause = (" WHERE " + " AND ".join(wheres)) if wheres else ""

    count_row = con.execute(
        f"SELECT COUNT(DISTINCT p.id) {base}{where_clause}", params
    ).fetchone()
    total = count_row[0] if count_row else 0

    select_cols = ", ".join(f"p.{c}" for c in _COLUMNS)
    rows = con.execute(
        f"SELECT DISTINCT {select_cols} {base}{where_clause} "
        f"ORDER BY p.{sort} {order} LIMIT ? OFFSET ?",
        params + [limit, offset],
    )

    return {"items": [_row_to_dict(r) for r in rows], "total": total}


def get_prompt(prompt_id: int) -> dict[str, Any] | None:
    """Return a single prompt by ID, or None."""
    con = get_pl_read_db()
    select_cols = ", ".join(_COLUMNS)
    row = con.execute(
        f"SELECT {select_cols} FROM prompt_library WHERE id=?", (prompt_id,)
    ).fetchone()
    if not row:
        return None
    result = _row_to_dict(row)

    # Attach folder IDs
    folders = con.execute(
        "SELECT folder_id FROM prompt_library_folder_items WHERE prompt_id=?",
        (prompt_id,),
    )
    result["folder_ids"] = [r[0] for r in folders]

    # Attach tag names
    tags = con.execute(
        "SELECT t.id, t.name FROM prompt_library_tags t "
        "JOIN prompt_library_tag_map tm ON tm.tag_id=t.id "
        "WHERE tm.prompt_id=?",
        (prompt_id,),
    )
    result["tags"] = [{"id": r[0], "name": r[1]} for r in tags]

    return result


def search_prompts(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """FTS search across title, positive, negative, memo."""
    con = get_pl_read_db()
    select_cols = ", ".join(f"p.{c}" for c in _COLUMNS)
    rows = con.execute(
        f"SELECT {select_cols} FROM prompt_library p "
        "WHERE p.id IN (SELECT rowid FROM prompt_library_fts WHERE prompt_library_fts MATCH ?) "
        "ORDER BY p.updated_at DESC LIMIT ?",
        (_fts5_phrase(query), limit),
    )
    return [_row_to_dict(r) for r in rows]
