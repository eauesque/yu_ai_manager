"""Prompt extraction helpers for share payloads."""

import json
from typing import Any

from core.prompt import parse_a1111_prompt, parse_novelai_v4_metadata


def _join_novelai_negative(v4_data: dict[str, Any]) -> str:
    """Reconstruct negative prompt from parsed NAI V4 metadata."""
    parts = []
    if v4_data.get("negative_base"):
        parts.append(v4_data["negative_base"])
    for nc in v4_data.get("negative_characters", []):
        if nc.get("prompt"):
            parts.append(nc["prompt"])
    return ", ".join(parts)


def extract_share_prompt_data(tmpl_row) -> tuple[str, str, str, dict[str, Any]]:
    raw_prompt = tmpl_row["raw_prompt"] or ""
    raw_negative = tmpl_row["raw_negative"] or ""
    model = tmpl_row["model_name"] or ""

    params: dict[str, Any] = {}
    positive = raw_prompt
    negative = raw_negative

    if "Steps:" in raw_prompt:
        parsed = parse_a1111_prompt(raw_prompt)
        params = parsed.get("parameters", {})
        positive = parsed.get("positive", raw_prompt)
        negative = parsed.get("negative", negative)
        if not model:
            model = params.get("Model", "")

    if tmpl_row["raw_meta_json"]:
        try:
            meta = json.loads(tmpl_row["raw_meta_json"])
            if not model and "model" in meta:
                model = meta.get("model", "")
            if not params.get("Seed") and "seed" in meta:
                params["Seed"] = str(meta["seed"])
            if not params.get("Steps") and "steps" in meta:
                params["Steps"] = str(meta["steps"])
            if not params.get("CFG scale") and "cfg_scale" in meta:
                params["CFG scale"] = str(meta["cfg_scale"])
            if not params.get("Sampler") and "sampler" in meta:
                params["Sampler"] = meta["sampler"]
            if not params.get("Size") and "width" in meta:
                params["Size"] = f"{meta['width']}x{meta['height']}"
        except (json.JSONDecodeError, KeyError):
            pass

    # NAI V4: reconstruct negative from raw_meta_json if missing
    if not negative and tmpl_row["raw_meta_json"]:
        v4_data = parse_novelai_v4_metadata(tmpl_row["raw_meta_json"])
        if v4_data:
            negative = _join_novelai_negative(v4_data)

    return positive, negative, model, params
