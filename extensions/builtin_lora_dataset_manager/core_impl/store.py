"""Database operations for LoRA projects and tag presets."""

from __future__ import annotations

import json
import logging

from core.services_core.db_state import get_db, get_readonly_db
from core.services_core.db_write import submit_db_write
from core.services_core.lora_dataset_write_service import (
    create_lora_preset_row,
    create_lora_project_row,
    delete_lora_preset_row,
    delete_lora_project_row,
    update_lora_preset_row,
    update_lora_project_row,
)

from .types import LoraProject

logger = logging.getLogger(__name__)

_PROJECT_COLUMNS = (
    "id, name, concept, repeat, base_model, model_scope, tag_exclude, tag_preset, "
    "search_query, file_ids, created_at, updated_at"
)
_PROJECT_COLUMNS_LEGACY = (
    "id, name, concept, repeat, base_model, 'all' AS model_scope, "
    "tag_exclude, tag_preset, search_query, file_ids, created_at, updated_at"
)
_PRESET_COLUMNS = "id, name, tags, created_at, updated_at"


def _project_columns(con) -> str:
    columns = {
        row[1]
        for row in con.execute("PRAGMA table_info(lora_projects)")
    }
    return _PROJECT_COLUMNS if "model_scope" in columns else _PROJECT_COLUMNS_LEGACY


def _row_to_project(row: dict) -> LoraProject:
    """Convert a DB row to LoraProject."""
    return LoraProject(
        id=row["id"],
        name=row["name"],
        concept=row["concept"],
        repeat=row["repeat"],
        base_model=row["base_model"],
        model_scope=row["model_scope"] or "all",
        tag_exclude=json.loads(row["tag_exclude"] or "[]"),
        tag_preset=row["tag_preset"] or "",
        search_query=row["search_query"] or "",
        file_ids=json.loads(row["file_ids"] or "[]"),
        created_at=row["created_at"] or 0,
        updated_at=row["updated_at"] or 0,
    )


# -- Project CRUD --

def list_projects() -> list[LoraProject]:
    """Return all projects ordered by updated_at desc."""
    con = get_readonly_db()
    rows = con.execute(
        f"SELECT {_project_columns(con)} FROM lora_projects ORDER BY updated_at DESC"
    )
    return [_row_to_project(r) for r in rows]


def get_project(project_id: int) -> LoraProject | None:
    """Return a single project or None."""
    con = get_readonly_db()
    row = con.execute(
        f"SELECT {_project_columns(con)} FROM lora_projects WHERE id = ?", (project_id,)
    ).fetchone()
    return _row_to_project(row) if row else None


def create_project(
    name: str,
    concept: str,
    base_model: str = "sdxl",
    repeat: int = 10,
    model_scope: str = "active",
) -> LoraProject:
    """Create a new project and return it."""
    project_id = submit_db_write(
        lambda: create_lora_project_row(
            name,
            concept,
            base_model=base_model,
            repeat=repeat,
            model_scope=model_scope,
            get_db_fn=get_db,
        )
    )
    return get_project(project_id)  # type: ignore[return-value]


def update_project(project_id: int, **fields) -> LoraProject | None:
    """Update project fields. JSON fields are auto-serialized."""
    allowed = {"name", "concept", "repeat", "base_model", "tag_exclude",
               "tag_preset", "search_query", "file_ids", "model_scope"}
    updates = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("tag_exclude", "file_ids"):
            updates[k] = json.dumps(v, ensure_ascii=False)
        else:
            updates[k] = v
    if not updates:
        return get_project(project_id)
    submit_db_write(lambda: update_lora_project_row(project_id, fields, get_db_fn=get_db))
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    """Delete a project. Returns True if deleted."""
    return submit_db_write(
        lambda: delete_lora_project_row(project_id, get_db_fn=get_db)
    ) > 0


# -- Tag Presets --

def list_presets() -> list[dict]:
    """Return all tag presets."""
    con = get_readonly_db()
    rows = con.execute(
        f"SELECT {_PRESET_COLUMNS} FROM lora_tag_presets ORDER BY name"
    )
    return [
        {"id": r["id"], "name": r["name"],
         "tags": json.loads(r["tags"] or "[]"),
         "created_at": r["created_at"], "updated_at": r["updated_at"]}
        for r in rows
    ]


def get_preset(preset_id: int) -> dict | None:
    """Return a single preset or None."""
    con = get_readonly_db()
    row = con.execute(
        f"SELECT {_PRESET_COLUMNS} FROM lora_tag_presets WHERE id = ?", (preset_id,)
    ).fetchone()
    if not row:
        return None
    return {"id": row["id"], "name": row["name"],
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def create_preset(name: str, tags: list[str]) -> dict:
    """Create a new tag preset."""
    preset_id = submit_db_write(
        lambda: create_lora_preset_row(name, tags, get_db_fn=get_db)
    )
    return get_preset(preset_id)  # type: ignore[return-value]


def update_preset(
    preset_id: int,
    name: str | None = None,
    tags: list[str] | None = None,
) -> dict | None:
    """Update preset fields."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if tags is not None:
        updates["tags"] = json.dumps(tags, ensure_ascii=False)
    if not updates:
        return get_preset(preset_id)
    submit_db_write(
        lambda: update_lora_preset_row(
            preset_id,
            name=name,
            tags=tags,
            get_db_fn=get_db,
        )
    )
    return get_preset(preset_id)


def delete_preset(preset_id: int) -> bool:
    """Delete a preset. Returns True if deleted."""
    return submit_db_write(
        lambda: delete_lora_preset_row(preset_id, get_db_fn=get_db)
    ) > 0
