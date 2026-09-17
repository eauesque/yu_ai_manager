"""Gradio 4 (Forge new) parameter mapping utilities.

Forge's new main branch (Gradio 4.x) removed most ``/sdapi/v1/`` endpoints.
Generation is done via ``POST /run/{api_name}`` with positional arrays.
This module handles the mapping between named parameters and array positions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# -- Known parameter positions for /txt2img (Forge main, Gradio 4) ----------
# Discovered dynamically from ``GET /info`` named_endpoints.
# These serve as a **fallback** when /info parsing fails.
_TXT2IMG_KNOWN: dict[str, int] = {
    "parameter_65": 0,
    "Prompt": 1,
    "Negative prompt": 2,
    "Styles": 3,
    "Batch count": 4,
    "Batch size": 5,
    "CFG Scale": 6,
    "Distilled CFG Scale": 7,
    "Height": 8,
    "Width": 9,
    "Hires. fix": 10,
    "Denoising strength": 11,
    "Upscale by": 12,
    "Upscaler": 13,
    "Hires steps": 14,
    "Resize width to": 15,
    "Resize height to": 16,
    "Sampling steps": 27,
    "Sampling method": 28,
    "Schedule type": 29,
    "Seed": 33,
}

# Minimum array length for txt2img call
_TXT2IMG_MIN_LEN = 40


def parse_endpoint_schema(
    info_response: dict, endpoint_name: str,
) -> dict[str, int] | None:
    """Parse ``GET /info`` response into a label-to-index map.

    Returns None if the endpoint is not found or parsing fails.
    """
    try:
        named = info_response.get("named_endpoints", {})
        ep = named.get(endpoint_name)
        if ep is None:
            return None
        params = ep.get("parameters", [])
        if not params:
            return None
        return {p.get("label", f"_unknown_{i}"): i for i, p in enumerate(params)}
    except Exception as exc:
        logger.warning("parse_endpoint_schema(%s) failed: %s", endpoint_name, exc)
        return None


def extract_sampler_choices(
    info_response: dict, endpoint_name: str = "/txt2img",
) -> list[str]:
    """Extract sampler enum values from the Sampling method parameter."""
    try:
        named = info_response.get("named_endpoints", {})
        ep = named.get(endpoint_name, {})
        params = ep.get("parameters", [])
        for p in params:
            if p.get("label") == "Sampling method":
                enums = p.get("type", {}).get("enum", [])
                return [str(e) for e in enums if e]
        return []
    except Exception:
        return []


def extract_model_choices(info_response: dict) -> list[str]:
    """Extract checkpoint model names from /gr_refresh_models endpoint."""
    try:
        named = info_response.get("named_endpoints", {})
        ep = named.get("/gr_refresh_models", {})
        returns = ep.get("returns", [])
        for r in returns:
            if r.get("label") == "Checkpoint":
                enums = r.get("type", {}).get("enum", [])
                return [str(e) for e in enums if e]
        return []
    except Exception:
        return []


def extract_upscaler_choices(
    info_response: dict, endpoint_name: str = "/txt2img",
) -> list[str]:
    """Extract upscaler enum values from the Upscaler parameter."""
    try:
        named = info_response.get("named_endpoints", {})
        ep = named.get(endpoint_name, {})
        params = ep.get("parameters", [])
        for p in params:
            if p.get("label") == "Upscaler":
                enums = p.get("type", {}).get("enum", [])
                return [str(e) for e in enums if e]
        return []
    except Exception:
        return []


def build_txt2img_args(
    schema_map: dict[str, int] | None,
    *,
    prompt: str = "",
    negative_prompt: str = "",
    steps: int = 28,
    sampler_name: str = "Euler a",
    cfg_scale: float = 7.0,
    width: int = 512,
    height: int = 768,
    seed: int = -1,
    batch_count: int = 1,
    batch_size: int = 1,
    enable_hr: bool = False,
    denoising_strength: float = 0.7,
    hr_scale: float = 2.0,
    hr_upscaler: str = "Latent",
    hr_second_pass_steps: int = 0,
    total_params: int = 0,
) -> list[Any]:
    """Build a positional argument array for ``POST /run/txt2img``.

    Uses *schema_map* (from :func:`parse_endpoint_schema`) if available,
    falling back to :data:`_TXT2IMG_KNOWN`.
    """
    pmap = schema_map or _TXT2IMG_KNOWN
    length = max(total_params, _TXT2IMG_MIN_LEN, max(pmap.values()) + 1)

    # Start with empty/default values
    args: list[Any] = [None] * length

    # Fill known positions
    _set(args, pmap, "Prompt", prompt)
    _set(args, pmap, "Negative prompt", negative_prompt)
    _set(args, pmap, "Sampling steps", steps)
    _set(args, pmap, "Sampling method", sampler_name)
    _set(args, pmap, "CFG Scale", cfg_scale)
    _set(args, pmap, "Width", width)
    _set(args, pmap, "Height", height)
    _set(args, pmap, "Seed", seed)
    _set(args, pmap, "Batch count", batch_count)
    _set(args, pmap, "Batch size", batch_size)
    _set(args, pmap, "Styles", [])

    # Hires Fix
    _set(args, pmap, "Hires. fix", enable_hr)
    if enable_hr:
        _set(args, pmap, "Denoising strength", denoising_strength)
        _set(args, pmap, "Upscale by", hr_scale)
        _set(args, pmap, "Upscaler", hr_upscaler)
        _set(args, pmap, "Hires steps", hr_second_pass_steps)

    return args


def _set(
    args: list[Any], pmap: dict[str, int], label: str, value: Any,
) -> None:
    """Set value at the mapped position, silently skip if label unknown."""
    idx = pmap.get(label)
    if idx is not None and idx < len(args):
        args[idx] = value
