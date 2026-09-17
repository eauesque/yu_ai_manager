"""Parsing utilities for NovelAI v3 (legacy) metadata."""

import json
from typing import Any

from novelai_v3_parse_builders import build_nai_chunk_result, build_png_result, build_webp_result


def is_v4_payload(data: dict[str, Any]) -> bool:
    return "v4_prompt" in data or "v4_negative_prompt" in data


def try_png_old_format(comment: str, description: str = "") -> dict[str, Any] | None:
    """Parse legacy NovelAI PNG comment payload."""
    try:
        data = json.loads(comment)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None
    if is_v4_payload(data):
        return None
    if "prompt" not in data and "uc" not in data:
        return None

    return build_png_result(comment, description, data)


def _looks_like_comfy_workflow_payload(outer: dict[str, Any]) -> bool:
    """Reject yu_ai_manager bridge YU_META payloads from ComfyUI.

    YU bridge wraps ComfyUI metadata as ``{"prompt": "<workflow JSON>", "workflow": "..."}``
    where ``prompt`` is itself a JSON-encoded ComfyUI workflow dict. NovelAI v3
    payloads have a *flat string* prompt (comma-separated tags), so a
    JSON-object/array-shaped value is a strong signal we are looking at
    ComfyUI data and must defer to the comfy parser (priority 110).
    Without this guard, NovelAI v3 (priority 60) would win the exclusive
    dispatch and dump the entire workflow JSON into raw_prompt.
    """
    if "workflow" in outer:
        return True
    pv = outer.get("prompt")
    if isinstance(pv, str):
        s = pv.lstrip()
        if s.startswith("{") or s.startswith("["):
            return True
    return False


def try_webp_old_format(raw_meta: str) -> dict[str, Any] | None:
    """Parse legacy NovelAI WebP payload (double JSON or direct JSON)."""
    try:
        outer = json.loads(raw_meta)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(outer, dict):
        return None

    if "Comment" in outer:
        try:
            inner = json.loads(outer["Comment"])
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(inner, dict) or is_v4_payload(inner):
            return None
        if "prompt" in inner or "uc" in inner:
            return build_webp_result(raw_meta, inner)

    if is_v4_payload(outer):
        return None
    if _looks_like_comfy_workflow_payload(outer):
        return None
    if "prompt" in outer or "uc" in outer:
        return build_webp_result(raw_meta, outer)

    return None


def try_webp_nai_json(nai_json: str, prompt: str, negative: str) -> dict[str, Any] | None:
    """Parse extracted nai_json/chunk fallback for legacy WebP."""
    if not (prompt or negative):
        return None

    payload: dict[str, Any] = {"prompt": prompt, "uc": negative}
    try:
        nai_data = json.loads(nai_json)
        if isinstance(nai_data, dict):
            payload.update(nai_data)
    except (json.JSONDecodeError, TypeError):
        pass

    if is_v4_payload(payload):
        return None

    return build_nai_chunk_result(nai_json, prompt, negative, payload)


def extract_params(data: dict[str, Any]) -> dict[str, str]:
    """Extract inspect parameter table from metadata payload."""
    params: dict[str, str] = {}
    for key in (
        "steps",
        "scale",
        "seed",
        "sampler",
        "noise_schedule",
        "sm",
        "sm_dyn",
        "cfg_rescale",
        "width",
        "height",
    ):
        if key in data:
            params[key] = str(data[key])
    return params
