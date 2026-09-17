"""Convert a recipe dict to Bridge-native generate body."""
from __future__ import annotations

from typing import Any

_GENERATE_URLS: dict[str, str] = {
    "nai": "/ext/nai-bridge/api/generate",
    "sd-webui": "/ext/sd-webui/api/generate",
    "comfyui": "/ext/comfyui-bridge/api/generate",
}

_BRIDGE_EXT_NAMES: dict[str, str] = {
    "nai": "builtin-nai-bridge",
    "sd-webui": "builtin-sd-webui-bridge",
    "comfyui": "builtin-comfyui-bridge",
}

SUPPORTED_SCHEMA = "yu://recipe/1"


def _is_extension_enabled(bridge_id: str) -> bool:
    from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
    ext_name = _BRIDGE_EXT_NAMES.get(bridge_id)
    if ext_name is None:
        return False
    enabled = get_extension_config_value(ext_name, "enabled")
    # None means config not set -> treat as enabled (default state)
    return bool(enabled) if enabled is not None else True


def fill_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Convert recipe to import response: {bridge_id, generate_url, generate_body, import_warnings}.

    Returns generate_url=None and generate_body=None when the bridge is disabled
    or the recipe cannot be routed, so callers must check generate_url before POSTing.
    """
    schema = recipe.get("schema", "")
    if schema != SUPPORTED_SCHEMA:
        raise ValueError(f"unsupported schema: {schema!r}")

    bridge_id = recipe.get("bridge_id", "")
    if not bridge_id:
        raise ValueError("recipe is missing bridge_id")
    if bridge_id not in _GENERATE_URLS:
        raise ValueError(f"unknown bridge_id: {bridge_id!r}")

    import_warnings: list[str] = []

    if not _is_extension_enabled(bridge_id):
        # tensor_art and other content warnings are intentionally omitted when
        # the extension is disabled — the caller cannot generate anyway.
        return {
            "bridge_id": bridge_id,
            "generate_url": None,
            "generate_body": None,
            "import_warnings": ["extension_disabled"],
        }

    prompt = recipe.get("positive", "")
    negative = recipe.get("negative", "")
    seed = recipe.get("seed")
    steps = recipe.get("steps")
    cfg = recipe.get("cfg")
    sampler = recipe.get("sampler", "")
    width = recipe.get("width")
    height = recipe.get("height")
    model = recipe.get("model", "")
    scheduler = recipe.get("scheduler")
    meta_source = recipe.get("_meta_source", "")

    if meta_source == "tensor_art":
        import_warnings.append("model_likely_unavailable_locally")

    if bridge_id == "nai":
        body: dict[str, Any] = {"prompt": prompt, "negative_prompt": negative, "model": model}
        if seed is not None:
            body["seed"] = seed
        if steps is not None:
            body["steps"] = steps
        if cfg is not None:
            body["scale"] = cfg
        if sampler:
            body["sampler"] = sampler
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height

    elif bridge_id == "sd-webui":
        body = {"prompt": prompt, "negative_prompt": negative}
        if seed is not None:
            body["seed"] = seed
        if steps is not None:
            body["steps"] = steps
        if cfg is not None:
            body["cfg_scale"] = cfg
        if sampler:
            body["sampler_name"] = sampler
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height
        import_warnings.append("model_switch_required")

    elif bridge_id == "comfyui":
        body = {"prompt": prompt, "negative_prompt": negative}
        if seed is not None:
            body["seed"] = seed
        if steps is not None:
            body["steps"] = steps
        if cfg is not None:
            body["cfg"] = cfg
        if sampler:
            body["sampler_name"] = sampler
        if scheduler:
            body["scheduler"] = scheduler
        import_warnings.append("model_switch_unsupported")

    else:
        # bridge_id was validated against _GENERATE_URLS above; this branch is unreachable
        raise ValueError(f"unknown bridge_id: {bridge_id!r}")

    return {
        "bridge_id": bridge_id,
        "generate_url": _GENERATE_URLS[bridge_id],
        "generate_body": body,
        "import_warnings": import_warnings,
    }
