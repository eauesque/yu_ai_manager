"""Prompt conversion helpers for file routes."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from importlib import import_module as _im

# Import from relocated sd-nai-convert extension
_sd_nai_engine = _im("extensions.builtin_sd_nai_convert.core_impl.sd_nai_convert_engine")
convert_nai_to_sd = _sd_nai_engine.convert_nai_to_sd
convert_sd_to_nai = _sd_nai_engine.convert_sd_to_nai
_sd_nai_warnings = _im("extensions.builtin_sd_nai_convert.core_impl.sd_nai_syntax_warnings")
_detect_syntax_warnings = _sd_nai_warnings.detect_syntax_warnings
from core.prompt.convert import expand_dynamic_prompt

_MAX_PROMPT_CHARS = 8192


def convert_prompt_payload(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Build payload for /api/convert."""
    if not data or "prompt" not in data or "mode" not in data:
        return {"error": "Invalid request", "code": "invalid_request"}, 400

    prompt = data["prompt"]
    mode = data["mode"]
    if not isinstance(prompt, str):
        return {"error": "prompt must be a string", "code": "invalid_prompt"}, 400
    if len(prompt) > _MAX_PROMPT_CHARS:
        return {
            "error": f"Prompt too long (max {_MAX_PROMPT_CHARS} chars)",
            "code": "prompt_too_long",
        }, 400

    try:
        warnings = []
        if mode in ("nai_to_sd", "sd_to_nai"):
            warnings = _detect_syntax_warnings(prompt, mode)

        if mode == "nai_to_sd":
            result = convert_nai_to_sd(prompt)
        elif mode == "sd_to_nai":
            result = convert_sd_to_nai(prompt)
        elif mode == "expand":
            seed = data.get("seed")
            result = expand_dynamic_prompt(prompt, seed)
        else:
            return {"error": "Invalid mode", "code": "invalid_mode"}, 400

        resp = {"result": result}
        if warnings:
            resp["warnings"] = warnings
        return resp, 200
    except Exception:
        logger.exception("File conversion failed")
        return {"error": "Conversion failed", "code": "convert_failed"}, 500
