"""Model registry REST routes for the ComfyUI bridge.

Endpoints:
  GET  /api/model-registry          — merged registry + available models from ComfyUI
  POST /api/model-registry          — upsert a user registry entry
  DELETE /api/model-registry/<id>   — remove a user registry entry
"""

from __future__ import annotations

import logging
import math
import re
from urllib.parse import urlparse

from quart import request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0a-\x0d\x0e-\x1f]")  # control chars except \t (tab)

_MAX_PATTERNS = 32
_MAX_PATTERN_LEN = 128
_MAX_FIELD_LEN = 256
_MAX_NOTES_LEN = 2000
_SOURCE_URL_SCHEMES = {"http", "https"}


def _is_valid_id(value: str) -> bool:
    return bool(_ID_RE.match(value))


def _has_ctrl(value: str) -> bool:
    return bool(_CTRL_RE.search(value))


def _validate_post_body(data: dict) -> str | None:
    """Validate POST body fields; return error string on first violation or None."""
    # unet_patterns
    patterns = data.get("unet_patterns")
    if isinstance(patterns, list):
        if len(patterns) > _MAX_PATTERNS:
            return f"'unet_patterns' must not exceed {_MAX_PATTERNS} items"
        for p in patterns:
            ps = str(p)
            if len(ps) > _MAX_PATTERN_LEN:
                return f"each pattern in 'unet_patterns' must not exceed {_MAX_PATTERN_LEN} characters"
            if _has_ctrl(ps):
                return "patterns must not contain control characters"

    # string fields with max length
    for field in ("vae", "clip_1", "clip_2", "clip_type", "latent_node", "source_url",
                  "default_sampler", "default_scheduler"):
        val = data.get(field)
        if val is not None:
            vs = str(val)
            if len(vs) > _MAX_FIELD_LEN:
                return f"'{field}' must not exceed {_MAX_FIELD_LEN} characters"
            if _has_ctrl(vs):
                return f"'{field}' must not contain control characters"

    source_url = str(data.get("source_url") or "").strip()
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme.lower() not in _SOURCE_URL_SCHEMES:
            return "'source_url' must use http or https"
        if not parsed.netloc:
            return "'source_url' must include a host"

    notes = data.get("notes")
    if notes is not None:
        ns = str(notes)
        if len(ns) > _MAX_NOTES_LEN:
            return f"'notes' must not exceed {_MAX_NOTES_LEN} characters"
        if _has_ctrl(ns):
            return "'notes' must not contain control characters"

    # numeric fields: reject NaN / Inf
    cfg = data.get("default_cfg")
    if cfg is not None:
        try:
            cfg_f = float(cfg)
        except (TypeError, ValueError):
            return "'default_cfg' must be a number"
        if not math.isfinite(cfg_f):
            return "'default_cfg' must be a finite number"

    steps = data.get("default_steps")
    if steps is not None:
        try:
            steps_i = int(steps)
        except (TypeError, ValueError):
            return "'default_steps' must be an integer"
        if steps_i < 1 or steps_i > 10000:
            return "'default_steps' must be between 1 and 10000"

    return None


def register_model_registry_routes(bp, *, require_admin_scope, make_client) -> None:
    try:
        from .comfyui_model_registry import (
            _entry_to_dict,
            delete_user_entry,
            get_merged_registry,
            upsert_user_entry,
        )
    except ImportError:  # pragma: no cover - top-level extension import path
        from comfyui_model_registry import (  # type: ignore[no-redef]
            _entry_to_dict,
            delete_user_entry,
            get_merged_registry,
            upsert_user_entry,
        )

    @bp.route("/api/model-registry", methods=["GET"])
    async def api_get_model_registry():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        merged = get_merged_registry()
        registry_list = [_entry_to_dict(e) for e in merged]

        # Fetch available models from ComfyUI (best-effort; empty on failure)
        available_models: dict = {"diffusion_models": [], "vaes": [], "text_encoders": []}
        models_error: str | None = None
        try:
            client = make_client()
            available_models["diffusion_models"] = (
                client.list_models_by_loader("UNETLoader", "unet_name") or []
            )
            available_models["vaes"] = (
                client.list_models_by_loader("VAELoader", "vae_name") or []
            )
            available_models["text_encoders"] = client.list_text_encoders() or []
        except Exception as exc:
            models_error = str(exc)
            logger.debug("Could not fetch available models for registry response: %s", exc)

        payload: dict = {"registry": registry_list, "available_models": available_models}
        if models_error:
            payload["models_error"] = models_error
        return api_success(payload)

    @bp.route("/api/model-registry", methods=["POST"])
    async def api_set_model_registry_entry():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])

        entry_id = str(data.get("id") or "").strip()
        if not entry_id:
            return api_error("'id' is required", 400)
        if not _is_valid_id(entry_id):
            return api_error(
                "'id' must be 1–64 characters: letters, digits, hyphens, or underscores",
                400,
            )

        # Require at least one pattern
        patterns_raw = data.get("unet_patterns") or data.get("unet_pattern")
        if not patterns_raw:
            return api_error("'unet_patterns' is required (list of substring patterns)", 400)

        validation_err = _validate_post_body(data)
        if validation_err:
            return api_error(validation_err, 400)

        try:
            entry, created = upsert_user_entry(data)
        except ValueError as exc:
            return api_error(str(exc), 400)

        return api_success({"entry": _entry_to_dict(entry), "created": created}, 201 if created else 200)

    @bp.route("/api/model-registry/<entry_id>", methods=["DELETE"])
    async def api_delete_model_registry_entry(entry_id: str):
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err

        if not _is_valid_id(entry_id):
            return api_error("Invalid entry id", 400)

        try:
            deleted = delete_user_entry(entry_id)
        except ValueError as exc:
            return api_error(str(exc), 400)

        if not deleted:
            return api_error(f"Entry '{entry_id}' not found in user registry", 404)

        return api_success({"deleted": True, "id": entry_id})
