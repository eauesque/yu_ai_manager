"""Quart blueprint factory for the NAI Bridge extension.

Route definitions and config endpoints. Generation logic is in nai_api_generate.
"""

from __future__ import annotations

import logging

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)
from quart import Blueprint, jsonify, render_template, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

# Re-export for backward compatibility
from .nai_api_generate import _copy_param, handle_generate  # noqa: F401
from .nai_client import NAIClient
from .nai_params import (
    DEFAULT_MODEL,
    MODEL_DISPLAY_NAMES,
    MODELS,
    NOISE_SCHEDULE_DISPLAY_NAMES,
    NOISE_SCHEDULES,
    SAMPLER_DISPLAY_NAMES,
    SAMPLERS,
)

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-nai-bridge"
_BRIDGE_TAG = "nai-api"
_SAVE_NAMING_OPTIONS = {"daily_folder"}
_IMAGE_FORMAT_OPTIONS = {"png", "webp", "jpg"}
_MASKED_TOKEN_SENTINELS = {"***", "****", "..."}


def _get_token() -> str:
    from core.settings_core.secret_store import decrypt
    raw = get_extension_config_value(_EXT_NAME, "api_token", "") or ""
    return decrypt(raw)


def _make_client() -> NAIClient:
    return NAIClient(_get_token())


def _mask_token(token: str) -> str:
    """Mask an API token for safe display."""
    if not token or len(token) < 16:
        return "***"
    return token[:8] + "..." + token[-4:]


from core.bridge_core.bridge_handlers import (
    register_cancel as _register_cancel,
)
from core.bridge_core.bridge_handlers import (
    register_generate as _register_generate,
)
from core.bridge_core.bridge_handlers import (
    register_progress as _register_progress,
)
from core.event_bus import emit
from core.event_bus.event_types import GEN_CANCEL
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# Wire bridge id (matches JS body.bridge / LAN Cowork dispatch). Internal
# _BRIDGE_TAG = "nai-api" is kept for event source tagging.
_WIRE_BRIDGE_ID = "nai"


async def _handle_generate(data: dict):
    return await handle_generate(data, _get_token)


async def _handle_progress(_data: dict):
    # NAI is HTTP-only and offers no streaming progress endpoint, so the
    # progress handler simply reports an idle stub. Both routes (local and
    # peer-relay) get the same shape.
    return api_success({"progress": 0, "step": 0, "total_steps": 0, "status": "idle"})


async def _handle_cancel(_data: dict):
    # NAI HTTP API has no cancel endpoint either; the bridge can only stop
    # client-side polling. We emit GEN_CANCEL so listeners can react.
    emit(GEN_CANCEL, {"bridge": _BRIDGE_TAG}, source=_EXT_NAME)
    return api_success({"cancelled": True, "note": "client-side only"})


_register_generate(_WIRE_BRIDGE_ID, _handle_generate)
_register_progress(_WIRE_BRIDGE_ID, _handle_progress)
_register_cancel(_WIRE_BRIDGE_ID, _handle_cancel)


def create_nai_bridge_blueprint(import_name: str) -> Blueprint:
    """Create and return the NAI Bridge blueprint."""

    bp = Blueprint(
        "ext_nai_bridge",
        import_name,
        template_folder="templates",
    )

    # -- UI page ----------------------------------------------------

    @bp.route("/")
    async def bridge_ui():
        return await render_template("nai_bridge.html")

    # -- Info -------------------------------------------------------

    @bp.route("/info")
    async def bridge_info():
        return jsonify({
            "name": _EXT_NAME,
            "bridge": _BRIDGE_TAG,
        })

    # -- Connection test --------------------------------------------

    @bp.route("/api/test-connection", methods=["POST"])
    async def api_test_connection():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        token = _get_token()
        if not token:
            return api_error("API token is not configured", 400,
                             hint="Set your NAI API token in Settings")
        client = NAIClient(token)
        result = client.test_connection()
        if result["ok"]:
            return api_success(result)
        return api_error(result.get("error", "Connection failed"),
                          result.get("status", 502))

    # -- Anlas ------------------------------------------------------

    @bp.route("/api/anlas")
    async def api_anlas():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        token = _get_token()
        if not token:
            return api_error("API token is not configured", 400)
        client = NAIClient(token)
        result = client.get_anlas()
        if result["ok"]:
            return api_success(result)
        return api_error(result.get("error", "Failed to fetch Anlas"),
                          result.get("status", 502))

    # -- Static lists -----------------------------------------------

    @bp.route("/api/models")
    async def api_models():
        items = [
            {"id": m, "name": MODEL_DISPLAY_NAMES.get(m, m)}
            for m in MODELS
        ]
        return api_success({"models": items})

    @bp.route("/api/samplers")
    async def api_samplers():
        items = [
            {"id": s, "name": SAMPLER_DISPLAY_NAMES.get(s, s)}
            for s in SAMPLERS
        ]
        return api_success({"samplers": items})

    @bp.route("/api/noise-schedules")
    async def api_noise_schedules():
        items = [
            {"id": n, "name": NOISE_SCHEDULE_DISPLAY_NAMES.get(n, n)}
            for n in NOISE_SCHEDULES
        ]
        return api_success({"noise_schedules": items})

    # -- Generate ---------------------------------------------------

    @bp.route("/api/generate", methods=["POST"])
    async def api_generate():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        assert data is not None
        return await _handle_generate(data)

    @bp.route("/api/save-batch", methods=["POST"])
    async def api_save_batch():
        from .nai_api_generate import handle_save_batch
        return await handle_save_batch(request)

    # -- Vibe upload ------------------------------------------------

    _MAX_VIBE_UPLOAD_BYTES = 32 * 1024 * 1024  # 32 MB

    @bp.route("/api/vibe/upload", methods=["POST"])
    async def api_vibe_upload():
        """Accept a .naiv4vibe file, inject all encodings into the cache.

        Returns {vibes: [{model, source_image_b64, entries: [{
            information_extracted, strength, cache_key}]}]}
        so the frontend can preview the source image and show available
        info values without re-encoding.
        """
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        from . import nai_vibe_cache
        from .nai_vibe_file import NaiVibeFormatError, parse_vibe_any

        files = await request.files
        if "file" not in files:
            return api_error("file field is required", 400)

        # Size-cap before full read (app global is 100 MB, we want 32 MB here)
        raw = files["file"].stream.read(_MAX_VIBE_UPLOAD_BYTES + 1)
        if len(raw) > _MAX_VIBE_UPLOAD_BYTES:
            return api_error(
                f"file exceeds {_MAX_VIBE_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                413,
            )

        try:
            bundle = parse_vibe_any(raw)
        except NaiVibeFormatError as exc:
            return api_error(f"not a valid vibe file: {exc}", 400)

        import base64 as _b64
        vibes_out: list[dict] = []
        for parsed in bundle.vibes:
            entries_out: list[dict] = []
            for entry in parsed.entries:
                key = None
                try:
                    nai_vibe_cache.put(
                        parsed.source_image_bytes,
                        parsed.model,
                        entry.information_extracted,
                        entry.blob,
                    )
                    key = nai_vibe_cache.cache_key(
                        parsed.source_image_bytes,
                        parsed.model,
                        entry.information_extracted,
                    )
                except (OSError, ValueError) as exc:
                    logger.warning("nai_vibe_cache.put failed during upload: %s", exc)
                entries_out.append({
                    "information_extracted": entry.information_extracted,
                    "strength": parsed.import_strength,
                    "cache_key": key,
                })
            img_bytes = parsed.source_image_bytes
            mime = "image/png" if img_bytes[:4] == b"\x89PNG" else "image/jpeg"
            vibes_out.append({
                "model": parsed.model,
                "source_image_b64": _b64.b64encode(img_bytes).decode("ascii"),
                "source_image_mime": mime,
                "entries": entries_out,
            })

        return api_success(data={"vibes": vibes_out})

    _MAX_VIBE_DOWNLOAD_ITEMS = 5  # 1 Vibe Transfer slot + up to 4 Precise Reference cards

    @bp.route("/api/vibe/download", methods=["POST"])
    async def api_vibe_download():
        """Encode (or reuse the cache for) every active reference image and
        return them as a .naiv4vibe (1 item) or .naiv4vibeBundle (2+ items)
        file, so they can be re-uploaded later without paying for
        /ai/encode-vibe again.

        Body: {"model": "...", "items": [{"reference_image": b64,
        "reference_information_extracted": float, "reference_strength":
        float}, ...]}
        """
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err

        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        assert data is not None

        model = data.get("model")
        if model not in MODELS:
            return api_error("valid model is required", 400)
        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return api_error("items is required", 400)
        if len(raw_items) > _MAX_VIBE_DOWNLOAD_ITEMS:
            return api_error(
                f"at most {_MAX_VIBE_DOWNLOAD_ITEMS} items are supported", 400)

        import base64 as _b64

        decoded: list[tuple[bytes, float, float]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                return api_error("each item must be an object", 400)
            image_b64 = item.get("reference_image")
            if not image_b64 or not isinstance(image_b64, str):
                return api_error("reference_image is required", 400)
            try:
                info = round(float(item.get("reference_information_extracted", 1.0)), 2)
                strength = float(item.get("reference_strength", 0.6))
            except (TypeError, ValueError):
                return api_error("invalid strength/information_extracted", 400)
            if not (0.0 <= info <= 1.0):
                return api_error("reference_information_extracted out of range", 400)
            try:
                image_bytes = _b64.b64decode(image_b64)
            except Exception as exc:
                return api_error(f"invalid base64 image: {exc}", 400)
            decoded.append((image_bytes, info, strength))

        token = _get_token()
        if not token:
            return api_error("API token is not configured", 400)
        client = NAIClient(token)

        from core.bridge_core import BridgeConnectionError, BridgeHTTPError
        from core.infra_core.blocking_tasks import run_long_blocking_sync

        built: list[tuple[bytes, str, bytes, float, float]] = []
        for image_bytes, info, strength in decoded:
            try:
                # encode_vibe() makes a synchronous NAI HTTP call that can
                # take tens of seconds; run it off the event loop so it
                # doesn't stall other requests (same executor as generate()).
                encoded_b64 = await run_long_blocking_sync(
                    client.encode_vibe,
                    _b64.b64encode(image_bytes).decode("ascii"), info, model,
                )
            except BridgeConnectionError as exc:
                return api_error(f"encode-vibe: {exc}", 502)
            except BridgeHTTPError as exc:
                return api_error(f"encode-vibe failed: HTTP {exc.status}", 502)
            built.append((image_bytes, model, _b64.b64decode(encoded_b64), info, strength))

        if len(built) == 1:
            from .nai_vibe_file import build_naiv4vibe
            image_bytes, _model, blob, info, strength = built[0]
            payload = build_naiv4vibe(image_bytes, model, blob, info, strength)
            filename = "vibe.naiv4vibe"
        else:
            from .nai_vibe_file import build_naiv4vibebundle
            payload = build_naiv4vibebundle(built)
            filename = "vibe.naiv4vibebundle"

        from quart import Response
        return Response(
            payload,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # -- Config -----------------------------------------------------

    @bp.route("/api/config", methods=["GET"])
    async def api_get_config():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.settings_core.secret_store import decrypt, mask_secret
        token = get_extension_config_value(_EXT_NAME, "api_token", "")
        return api_success({
            "api_token": mask_secret(decrypt(token)) if token else "",
            "auto_send": get_extension_config_value(_EXT_NAME, "auto_send", False),
            "default_model": get_extension_config_value(
                _EXT_NAME, "default_model", DEFAULT_MODEL),
            "default_sampler": get_extension_config_value(
                _EXT_NAME, "default_sampler", SAMPLERS[0]),
            "default_noise_schedule": get_extension_config_value(
                _EXT_NAME, "default_noise_schedule", NOISE_SCHEDULES[0]),
            "save_folder": get_extension_config_value(
                _EXT_NAME, "save_folder", ""),
            "auto_save": get_extension_config_value(
                _EXT_NAME, "auto_save", False),
            "save_naming": get_extension_config_value(
                _EXT_NAME, "save_naming", "daily_folder"),
            "default_image_format": get_extension_config_value(
                _EXT_NAME, "default_image_format", "png"),
            "auto_import": get_extension_config_value(
                _EXT_NAME, "auto_import", True),
            "cache_max_size_mb": get_extension_config_value(
                _EXT_NAME, "cache_max_size_mb", 500),
            "block_anlas_on_v5_limit": get_extension_config_value(
                _EXT_NAME, "block_anlas_on_v5_limit", False),
        })

    @bp.route("/api/config", methods=["POST"])
    async def api_save_config():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        assert data is not None

        allowed = {
            "api_token", "auto_send",
            "default_model", "default_sampler", "default_noise_schedule",
            "save_folder", "auto_save", "save_naming", "default_image_format",
            "auto_import", "cache_max_size_mb", "block_anlas_on_v5_limit",
        }
        to_save = {k: v for k, v in data.items() if k in allowed}
        if not to_save:
            return api_error("No valid config fields provided", 400)

        # Encrypt new raw tokens while preserving encrypted or intentionally blank values.
        if "api_token" in to_save and isinstance(to_save["api_token"], str):
            raw = to_save["api_token"].strip()
            if raw.startswith("enc:"):
                to_save["api_token"] = raw
            elif raw == "":
                to_save["api_token"] = ""
            elif raw in _MASKED_TOKEN_SENTINELS or set(raw) == {"*"}:
                del to_save["api_token"]
            elif raw.startswith("pst-"):
                from core.settings_core.secret_store import encrypt
                to_save["api_token"] = encrypt(raw)
            else:
                logger.warning("Ignoring unrecognized NAI api_token value")
                del to_save["api_token"]
        for bool_field in ("auto_send", "auto_save", "auto_import", "block_anlas_on_v5_limit"):
            if bool_field in to_save and not isinstance(to_save[bool_field], bool):
                return api_error(f"{bool_field} must be a boolean", 400)
        if "default_model" in to_save:
            model = str(to_save["default_model"]).strip()
            if model not in MODELS:
                return api_error("default_model is invalid", 400)
            to_save["default_model"] = model
        if "default_sampler" in to_save:
            sampler = str(to_save["default_sampler"]).strip()
            if sampler not in SAMPLERS:
                return api_error("default_sampler is invalid", 400)
            to_save["default_sampler"] = sampler
        if "default_noise_schedule" in to_save:
            noise_schedule = str(to_save["default_noise_schedule"]).strip()
            if noise_schedule not in NOISE_SCHEDULES:
                return api_error("default_noise_schedule is invalid", 400)
            to_save["default_noise_schedule"] = noise_schedule
        if "save_folder" in to_save:
            if not isinstance(to_save["save_folder"], str):
                return api_error("save_folder must be a string", 400)
            to_save["save_folder"] = to_save["save_folder"].strip()
        if "save_naming" in to_save:
            naming = str(to_save["save_naming"]).strip()
            if naming not in _SAVE_NAMING_OPTIONS:
                return api_error("save_naming is invalid", 400)
            to_save["save_naming"] = naming
        if "default_image_format" in to_save:
            image_format = str(to_save["default_image_format"]).strip().lower()
            if image_format not in _IMAGE_FORMAT_OPTIONS:
                return api_error("default_image_format is invalid", 400)
            to_save["default_image_format"] = image_format
        if "cache_max_size_mb" in to_save:
            try:
                mb = float(to_save["cache_max_size_mb"])
            except (ValueError, TypeError):
                return api_error("cache_max_size_mb must be a number", 400)
            if mb < 0 or mb > 102400:
                return api_error("cache_max_size_mb must be 0–102400", 400)
            to_save["cache_max_size_mb"] = mb

        save_extension_config_values(_EXT_NAME, to_save)
        return api_success({"saved": list(to_save.keys())})

    return bp
