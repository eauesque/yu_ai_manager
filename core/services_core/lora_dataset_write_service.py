"""Write helpers for LoRA dataset manager persistence."""

from __future__ import annotations

import json
import time
from collections.abc import Callable


def create_lora_project_row(
    name: str,
    concept: str,
    *,
    base_model: str = "sdxl",
    repeat: int = 10,
    model_scope: str = "active",
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    now = int(time.time())
    con = get_db_fn()
    cur = con.execute(
        """INSERT INTO lora_projects
           (name, concept, base_model, repeat, model_scope, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, concept, base_model, repeat, model_scope, now, now),
    )
    con.commit()
    return cur.lastrowid


def update_lora_project_row(
    project_id: int,
    fields: dict,
    *,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    allowed = {
        "name", "concept", "repeat", "base_model", "tag_exclude",
        "tag_preset", "search_query", "file_ids", "model_scope",
    }
    updates = {}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in ("tag_exclude", "file_ids"):
            updates[key] = json.dumps(value, ensure_ascii=False)
        else:
            updates[key] = value
    if not updates:
        return
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [project_id]

    con = get_db_fn()
    con.execute(f"UPDATE lora_projects SET {set_clause} WHERE id = ?", values)
    con.commit()


def delete_lora_project_row(
    project_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    cur = con.execute("DELETE FROM lora_projects WHERE id = ?", (project_id,))
    con.commit()
    return cur.rowcount


def create_lora_preset_row(
    name: str,
    tags: list[str],
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    now = int(time.time())
    con = get_db_fn()
    cur = con.execute(
        """INSERT INTO lora_tag_presets (name, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?)""",
        (name, json.dumps(tags, ensure_ascii=False), now, now),
    )
    con.commit()
    return cur.lastrowid


def update_lora_preset_row(
    preset_id: int,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    get_db_fn: Callable | None = None,
) -> None:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    updates = {}
    if name is not None:
        updates["name"] = name
    if tags is not None:
        updates["tags"] = json.dumps(tags, ensure_ascii=False)
    if not updates:
        return
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [preset_id]

    con = get_db_fn()
    con.execute(f"UPDATE lora_tag_presets SET {set_clause} WHERE id = ?", values)
    con.commit()


def delete_lora_preset_row(
    preset_id: int,
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_state import get_db as get_db_fn

    con = get_db_fn()
    cur = con.execute("DELETE FROM lora_tag_presets WHERE id = ?", (preset_id,))
    con.commit()
    return cur.rowcount
