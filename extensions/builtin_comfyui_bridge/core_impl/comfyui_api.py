"""Quart blueprint factory for the ComfyUI Bridge extension.

Generation logic is split into comfyui_api_generate.py.
This module creates the blueprint and registers all routes.
"""

from __future__ import annotations

import logging

from core.extensions_core.extensions_admin import (
    get_extension_config_value as get_ext_config,  # alias for gateway helpers + tests
)
from quart import Blueprint, request

from core.infra_core.api_errors import api_error
from core.infra_core.api_request import require_json_dict
from core.infra_core.blocking_tasks import run_long_blocking_sync

from .comfyui_api_config_routes import register_config_routes
from .comfyui_api_generate import (  # noqa: F401 -- re-export
    convert_images as _convert_images,
)
from .comfyui_api_generate import (
    generate_json as _generate_json,
)
from .comfyui_api_generate import (
    generate_simple as _generate_simple,
)
from .comfyui_api_generate import (
    progress_state as _progress_state,
)
from .comfyui_api_info_routes import register_info_routes
from .comfyui_api_model_registry_routes import register_model_registry_routes
from .comfyui_api_upload_utils import read_upload_bytes_limited, validate_image_filename
from .comfyui_api_workflow_routes import register_workflow_routes
from .comfyui_client import ComfyUIClient
from .comfyui_discovery_api import register_comfyui_discovery_routes

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-comfyui-bridge"
_BRIDGE_TAG = "comfyui"
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024
_ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
# Save naming codes are owned by this Bridge so the static set stays.
_SAVE_NAMING_OPTIONS = {"daily_folder", "date_prefix", "timestamp"}
_IMAGE_FORMAT_OPTIONS = {"png", "webp", "jpg"}
# Sampler / scheduler enums are owned by ComfyUI itself (queryable via the
# /object_info endpoint and varying by installed custom nodes), so a static
# allow-list here just causes drift. Validation is reduced to "non-empty
# string"; ComfyUI rejects unknown names at workflow execution time.
_DEFAULT_SCHEDULER_OPTIONS: set[str] | None = None
_DEFAULT_SAMPLER_OPTIONS: set[str] | None = None


class GatewayUrlError(Exception):
    """Raised when gateway_url is configured but fails validation (fail-closed, no fallback)."""


def _get_api_url() -> str:
    """Return effective base URL for ComfyUI. Raises GatewayUrlError if gateway_url is invalid."""
    gw_url = get_ext_config(_EXT_NAME, "gateway_url", "")
    if gw_url:
        from core.gateway.bridge_validation import validate_comfy_gateway_url
        err = validate_comfy_gateway_url(gw_url)
        if err:
            raise GatewayUrlError(f"gateway_url invalid: {err}")
        return gw_url.rstrip("/")
    return get_ext_config(_EXT_NAME, "api_url", "http://127.0.0.1:8188")


def _get_api_key() -> str:
    """Return decrypted API key from api_key_enc config, or empty string."""
    raw = get_ext_config(_EXT_NAME, "api_key_enc", "")
    if not raw:
        return ""
    from core.settings_core.secret_store import decrypt, is_encrypted
    try:
        return decrypt(raw) if is_encrypted(raw) else ""
    except Exception:
        return ""


def _get_default_headers() -> dict[str, str]:
    """Return Authorization header if gateway api_key_enc is configured."""
    key = _get_api_key()
    return {"Authorization": f"Bearer {key}"} if key else {}


def _make_client(resolved_backend_id: str | None = None) -> ComfyUIClient:
    """Create ComfyUIClient. resolved_backend_id is fixed for task lifetime."""
    from core.gateway.backend_registry import FALLBACK_URLS, get_backend
    if resolved_backend_id and resolved_backend_id != "__fallback__":
        entry = get_backend(resolved_backend_id)
        url = entry["base_url"] if entry else FALLBACK_URLS["comfyui"]
    else:
        url = _get_api_url()
        resolved_backend_id = None
    return ComfyUIClient(url, backend_id=resolved_backend_id)


def _response_status_code(result) -> int:
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[1])
    if hasattr(result, "status_code"):
        return int(result.status_code)
    return 200


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


def _check_origin(req) -> bool:
    origin = req.headers.get("Origin", "")
    if not origin:
        return True
    from urllib.parse import urlparse

    from core.gateway.auth import _LOOPBACK_ADDRS

    o = urlparse(origin)
    if not o.hostname:
        return False
    return o.hostname in _LOOPBACK_ADDRS


async def _handle_generate(data: dict):
    """Bridge generate handler — invoked by both the local /api/generate route
    and the LAN Cowork /api/peer/generate relay. Same input → same output."""
    from quart import request as _req
    if not _check_origin(_req):
        from core.infra_core.api_errors import api_error
        return api_error("Forbidden", 403)

    from core.bridge_core import task_registry as _tr
    from core.gateway.backend_registry import resolve_backend

    task_id: str | None = data.get("task_id")
    backend_id_req: str | None = data.get("backend_id")

    resolved = resolve_backend("comfyui", backend_id_req)
    if resolved.error_kind == "not_found":
        from core.infra_core.api_errors import api_error
        return api_error(f"backend not found: {backend_id_req}", 404)
    if resolved.error_kind == "type_mismatch":
        from core.infra_core.api_errors import api_error
        return api_error(f"backend type mismatch: {backend_id_req}", 400)

    if task_id:
        ok = _tr.create_task(task_id, resolved.resolved_backend_id, resolved.base_url, "comfyui")
        if not ok:
            from core.infra_core.api_errors import api_error
            return api_error(f"task_id already registered: {task_id}", 409)

    mode = (data.get("mode") or "simple").strip().lower()
    resolved_id = resolved.resolved_backend_id if resolved.resolved_backend_id != "__fallback__" else None
    client = _make_client(resolved_id)
    if task_id:
        _tr.set_cancel_fn(task_id, client.interrupt)
    client_id = ComfyUIClient.new_client_id()
    # Use the dedicated long-blocking pool (not the default executor used by
    # /api/files/thumbnails-batch); a 300s wait_for_result on the default
    # pool starves index/thumbnail requests.
    def _run():
        if mode == "json":
            return _generate_json(data, client, client_id, task_id=task_id)
        return _generate_simple(data, client, client_id, task_id=task_id)

    try:
        result = await run_long_blocking_sync(_run)
        if task_id:
            try:
                status = _response_status_code(result)
                if status >= 400:
                    _tr.fail_task(task_id, f"generation returned HTTP {status}")
                else:
                    _tr.complete_task(task_id)
            except Exception:
                _tr.complete_task(task_id)
        return result
    except Exception as exc:
        if task_id:
            _tr.fail_task(task_id, str(exc))
        raise


async def _handle_progress(_data: dict):
    from core.infra_core.api_errors import api_success
    return api_success({
        "progress": _progress_state.get("progress", 0),
        "step": _progress_state.get("step", 0),
        "total_steps": _progress_state.get("total_steps", 0),
        "status": _progress_state.get("status", "idle"),
    })


async def _handle_cancel(_data: dict):
    from core.infra_core.api_errors import api_success
    client = _make_client()
    ok = client.interrupt()
    if ok:
        _progress_state["status"] = "cancelled"
        emit(GEN_CANCEL, {"bridge": _BRIDGE_TAG}, source=_EXT_NAME)
        return api_success({"cancelled": True})
    return api_error("Cancel request failed", 502)


_register_generate(_BRIDGE_TAG, _handle_generate)
_register_progress(_BRIDGE_TAG, _handle_progress)
_register_cancel(_BRIDGE_TAG, _handle_cancel)


def create_comfyui_bridge_blueprint(import_name: str) -> Blueprint:
    """Create and return the ComfyUI Bridge blueprint."""

    bp = Blueprint(
        "ext_comfyui_bridge",
        import_name,
        template_folder="templates",
    )

    register_info_routes(
        bp,
        make_client=_make_client,
        get_api_url=_get_api_url,
        progress_state=_progress_state,
        ext_name=_EXT_NAME,
        bridge_tag=_BRIDGE_TAG,
    )
    register_workflow_routes(
        bp,
        make_client=_make_client,
        read_upload_bytes_limited_fn=lambda storage, *, max_bytes: read_upload_bytes_limited(
            storage,
            max_bytes=max_bytes,
            chunk_size=_UPLOAD_CHUNK_SIZE,
        ),
        validate_image_filename_fn=lambda filename: validate_image_filename(
            filename,
            allowed_exts=_ALLOWED_IMAGE_EXTS,
        ),
        max_image_upload_bytes=_MAX_IMAGE_UPLOAD_BYTES,
    )
    register_config_routes(
        bp,
        require_admin_scope=_require_admin_scope,
        ext_name=_EXT_NAME,
        save_naming_options=_SAVE_NAMING_OPTIONS,
        image_format_options=_IMAGE_FORMAT_OPTIONS,
        default_scheduler_options=_DEFAULT_SCHEDULER_OPTIONS,
        default_sampler_options=_DEFAULT_SAMPLER_OPTIONS,
    )

    @bp.route("/api/save-batch", methods=["POST"])
    async def api_save_batch():
        from core.bridge_core.bridge_save import save_images
        from core.bridge_core.bridge_save_batch import handle_save_batch
        return await handle_save_batch(request, ext_name=_EXT_NAME, save_fn=save_images)

    @bp.route("/api/generate", methods=["POST"])
    async def api_generate():
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        return await _handle_generate(data)

    register_comfyui_discovery_routes(bp, _make_client)
    register_model_registry_routes(
        bp,
        require_admin_scope=_require_admin_scope,
        make_client=_make_client,
    )
    return bp
