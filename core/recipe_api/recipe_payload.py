"""Build a recipe dict from a file_id using existing FILE_DETAIL_SQL."""
from __future__ import annotations

import json
from typing import Any

from core.file_api.detail_payload_data import FILE_DETAIL_SQL

_NAI_SOURCES = frozenset({
    "novelai_v4_png", "novelai_png", "novelai_v4_webp", "novelai_webp",
    "novelai_v4", "nai_webp",
})
_A1111_PREFIX = "a1111_"
_COMFY_SOURCES = frozenset({
    "comfyui", "comfy_png", "comfy_webp", "comfy_webm", "comfy_flac",
})

SCHEMA = "yu://recipe/1"


def _meta_source_to_bridge_id(meta_source: str | None) -> str | None:
    if meta_source is None:
        return None
    if meta_source in _NAI_SOURCES:
        return "nai"
    if meta_source.startswith(_A1111_PREFIX) or meta_source == "tensor_art":
        return "sd-webui"
    if meta_source in _COMFY_SOURCES:
        return "comfyui"
    return None


def _normalize_parameters(params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Map display-label parameter keys to recipe fields.

    Unknown keys are appended to warnings (not a parse error, just unrecognised).
    Returns (normalized_fields, unknown_keys).
    """
    fields: dict[str, Any] = {}
    warnings: list[str] = []

    for key, val in params.items():
        if key in ("CFG scale", "scale"):
            try:
                fields["cfg"] = float(val)
            except (TypeError, ValueError):
                warnings.append(key)
        elif key == "Size" and isinstance(val, str) and "x" in val:
            try:
                w, h = val.split("x", 1)
                fields["width"] = int(w)
                fields["height"] = int(h)
            except (ValueError, TypeError):
                warnings.append(key)
        elif key == "Seed":
            try:
                fields["seed"] = int(val)
            except (TypeError, ValueError):
                warnings.append(key)
        elif key == "Steps":
            try:
                fields["steps"] = int(val)
            except (TypeError, ValueError):
                warnings.append(key)
        elif key == "Sampler":
            fields["sampler"] = str(val)
        elif key in ("Model", "model_name"):
            fields["model"] = str(val)
        else:
            warnings.append(key)

    return fields, warnings


def build_recipe(file_id: int, db: Any) -> dict[str, Any] | None:
    """Return a recipe dict for file_id, or None if the file has no gen metadata."""
    row = db.execute(FILE_DETAIL_SQL, (file_id,)).fetchone()
    if row is None:
        return None

    meta_source = row["meta_source"]
    bridge_id = _meta_source_to_bridge_id(meta_source)
    if bridge_id is None:
        return None

    recipe: dict[str, Any] = {
        "schema": SCHEMA,
        "bridge_id": bridge_id,
        "positive": row["raw_prompt"] or "",
        "negative": row["raw_negative"] or "",
        "capture_warnings": [],
    }

    model_name = row["model_name"]
    if model_name:
        recipe["model"] = model_name

    if bridge_id != "nai":
        model_hash = row["model_hash"]
        if model_hash:
            recipe["model_hash"] = model_hash

    raw_meta_json = row["raw_meta_json"]
    if raw_meta_json:
        try:
            meta = json.loads(raw_meta_json)
            params = meta.get("parameters", {})
            if isinstance(params, dict) and params:
                norm_fields, norm_warnings = _normalize_parameters(params)
                recipe.update(norm_fields)
                recipe["capture_warnings"].extend(norm_warnings)
        except (json.JSONDecodeError, TypeError):
            recipe["capture_warnings"].append("parse_error")

    return recipe
