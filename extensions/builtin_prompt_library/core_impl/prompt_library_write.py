"""Prompt Library write operations: create, update, delete."""

from __future__ import annotations

import json
import time
from typing import Any

from core.services_core.db_write import submit_db_write

from .prompt_library_db import get_pl_db


def _serialize_characters(characters: list[dict[str, Any]] | None) -> str:
    """Serialize characters list to JSON string for DB storage."""
    if not characters:
        return ""
    return json.dumps(characters, ensure_ascii=False, separators=(",", ":"))


def create_prompt(
    *,
    title: str,
    positive: str = "",
    negative: str = "",
    seed: str = "",
    steps: str = "",
    sampler: str = "",
    cfg_scale: str = "",
    model_name: str = "",
    memo: str = "",
    source_file_id: int | None = None,
    characters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Insert a new prompt and return its dict (with id)."""
    now = int(time.time())
    chars_json = _serialize_characters(characters)
    def _write() -> int:
        con = get_pl_db()
        cur = con.execute(
            "INSERT INTO prompt_library "
            "(title, positive, negative, seed, steps, sampler, cfg_scale, "
            " model_name, memo, source_file_id, characters_json, "
            " created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, positive, negative, seed, steps, sampler, cfg_scale,
             model_name, memo, source_file_id, chars_json, now, now),
        )
        con.commit()
        return cur.lastrowid

    prompt_id = submit_db_write(_write)
    return {
        "id": prompt_id, "title": title,
        "positive": positive, "negative": negative,
        "seed": seed, "steps": steps, "sampler": sampler,
        "cfg_scale": cfg_scale, "model_name": model_name,
        "memo": memo, "source_file_id": source_file_id,
        "characters": characters or [],
        "created_at": now, "updated_at": now,
    }


def update_prompt(prompt_id: int, **fields) -> dict[str, Any] | None:
    """Update a prompt's fields. Returns updated dict or None if not found."""
    allowed = {
        "title", "positive", "negative", "seed", "steps",
        "sampler", "cfg_scale", "model_name", "memo", "characters",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None

    if "characters" in updates:
        updates["characters_json"] = _serialize_characters(updates.pop("characters"))


    now = int(time.time())
    updates["updated_at"] = now

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [prompt_id]

    def _write() -> int:
        con = get_pl_db()
        cur = con.execute(
            f"UPDATE prompt_library SET {set_clause} WHERE id=?", values
        )
        if cur.rowcount == 0:
            return 0
        con.commit()
        return cur.rowcount

    if submit_db_write(_write) == 0:
        return None

    # Return fresh row
    from .prompt_library_read import get_prompt
    return get_prompt(prompt_id)


def delete_prompt(prompt_id: int) -> bool:
    """Delete a prompt. Returns True if deleted."""
    def _write() -> int:
        con = get_pl_db()
        cur = con.execute("DELETE FROM prompt_library WHERE id=?", (prompt_id,))
        con.commit()
        return cur.rowcount

    return submit_db_write(_write) > 0
