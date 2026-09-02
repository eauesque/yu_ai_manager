"""Quart blueprint factory for the SD WebUI Bridge extension.

Route definitions and config endpoints. Generation logic is in sd_webui_api_generate.
"""

from __future__ import annotations

import logging
import threading

from core.extensions_core.extensions_admin import (
    get_extension_config_value as get_ext_config,  # alias for gateway helpers + tests
)
from quart import Blueprint, request

from .sd_webui_api_config_routes import register_config_routes
from .sd_webui_api_generate import handle_generate  # noqa: F401
from .sd_webui_api_info_routes import register_info_routes
from .sd_webui_api_model_routes import register_model_routes
from .sd_webui_client import SDWebUIClient, create_client
from .sd_webui_discovery_api import register_sd_discovery_routes

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-sd-webui-bridge"
_BRIDGE_TAG = "sd-webui"
# Save naming codes are owned by this Bridge so the static set stays.
_SAVE_NAMING_OPTIONS = {"daily_folder", "date_prefix", "timestamp"}
_IMAGE_FORMAT_OPTIONS = {"png", "webp", "jpg"}
# Sampler list is owned by SD WebUI itself — keeping a static allow-list here
# only causes drift when the UI dropdown is updated. Validation is reduced to
# "non-empty string"; SD WebUI rejects unknown samplers at generation time.
_DEFAULT_SAMPLER_OPTIONS: set[str] | None = None

_cached_api_type: dict[str, str | None] = {}
_cached_api_url: str | None = None
_client_cache_lock = threading.Lock()


class GatewayUrlError(Exception):
    """Raised when gateway_url is configured but fails validation (fail-closed, no fallback)."""


def _get_api_url() -> str:
    """Return effective base URL for SD WebUI. Raises GatewayUrlError if gateway_url is invalid."""
    gw_url = get_ext_config(_EXT_NAME, "gateway_url", "")
    if gw_url:
        from core.gateway.bridge_validation import validate_sd_gateway_url
        err = validate_sd_gateway_url(gw_url)
        if err:
            raise GatewayUrlError(f"gateway_url invalid: {err}")
        return gw_url.rstrip("/")
    return get_ext_config(_EXT_NAME, "api_url", "http://127.0.0.1:7860")


def _get_default_headers() -> dict[str, str]:
    """Return Authorization header if gateway api_key_enc is configured."""
    raw = get_ext_config(_EXT_NAME, "api_key_enc", "")
    if not raw:
        return {}
    from core.settings_core.secret_store import decrypt, is_encrypted
    try:
        if not is_encrypted(raw):
            # Key is stored in plaintext (e.g. after a migration gap). Log a
            # warning but never log the raw value itself, then skip auth so the
            # caller gets a clear 401/502 rather than a silent empty response.
            logger.warning(
                "SD WebUI api_key_enc is not encrypted; "
                "re-save the key in Settings to fix authentication."
            )
            return {}
        key = decrypt(raw)
        return {"Authorization": f"Bearer {key}"} if key else {}
    except Exception:
        return {}


def _make_client(resolved_backend_id: str | None = None):
    """Create SD WebUI client with optional backend routing."""
    global _cached_api_url
    from core.gateway.backend_registry import FALLBACK_URLS, get_backend

    cache_key = resolved_backend_id or "__fallback__"
    if resolved_backend_id and resolved_backend_id != "__fallback__":
        entry = get_backend(resolved_backend_id)
        url = entry["base_url"] if entry else FALLBACK_URLS["sd_webui"]
    else:
        url = _get_api_url()

    extra_headers: dict[str, str] = {}
    if resolved_backend_id and resolved_backend_id != "__fallback__":
        extra_headers["X-Backend-Id"] = resolved_backend_id

    with _client_cache_lock:
        if cache_key == "__fallback__" and url != _cached_api_url:
            _cached_api_type.pop("__fallback__", None)
            _cached_api_url = url

        if cache_key in _cached_api_type and _cached_api_type[cache_key] is not None:
            if _cached_api_type[cache_key] == "gradio4":
                from .gradio4_client import Gradio4ForgeClient

                return Gradio4ForgeClient(url, extra_headers=extra_headers)
            return SDWebUIClient(url, extra_headers=extra_headers)

        client = create_client(url, extra_headers=extra_headers)
        _cached_api_type[cache_key] = client.api_type
        return client


def _reset_client_cache() -> None:
    global _cached_api_type, _cached_api_url
    with _client_cache_lock:
        _cached_api_type.clear()
        _cached_api_url = None
    # Forge save-suppression flags are tracked per api_url; clear them too
    # so a re-pointed bridge re-applies suppression on the new upstream.
    from .sd_webui_generate_helpers import reset_save_suppression_cache
    reset_save_suppression_cache()


def _on_backend_invalidated(backend_id: str, reason: str) -> None:
    with _client_cache_lock:
        _cached_api_type.pop(backend_id, None)


from core.gateway.backend_registry import register_invalidation_callback

register_invalidation_callback(_on_backend_invalidated)


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
from core.infra_core.api_errors import api_error, api_success
from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _check_origin(req) -> bool:
    origin = req.headers.get("Origin", "")
    if not origin:
        return True
    from urllib.parse import urlparse

    o = urlparse(origin)
    if not o.hostname:
        return False
    # Use a local constant rather than importing the private _LOOPBACK_ADDRS
    # symbol from core.gateway.auth to avoid fragile cross-module coupling.
    return o.hostname in {"127.0.0.1", "::1", "localhost"}


def _response_status_code(result) -> int:
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[1])
    if hasattr(result, "status_code"):
        return int(result.status_code)
    return 200


async def _handle_generate(data: dict):
    from quart import request as _req
    if not _check_origin(_req):
        return api_error("Forbidden", 403)

    from core.bridge_core import task_registry as _tr
    from core.gateway.backend_registry import resolve_backend

    task_id: str | None = data.get("task_id")
    backend_id_req: str | None = data.get("backend_id")

    resolved = resolve_backend("sd_webui", backend_id_req)
    if resolved.error_kind == "not_found":
        return api_error(f"backend not found: {backend_id_req}", 404)
    if resolved.error_kind == "type_mismatch":
        return api_error(f"backend type mismatch: {backend_id_req}", 400)

    if task_id:
        ok = _tr.create_task(task_id, resolved.resolved_backend_id, resolved.base_url, "sd_webui")
        if not ok:
            return api_error(f"task_id already registered: {task_id}", 409)

    resolved_id = resolved.resolved_backend_id if resolved.resolved_backend_id != "__fallback__" else None

    def _make_task_client():
        client = _make_client(resolved_id)
        if task_id:
            _tr.set_cancel_fn(task_id, client.interrupt)
        return client

    from .sd_webui_api_generate import handle_generate as _gen
    try:
        result = await _gen(data, _make_task_client)
        if task_id:
            status = _response_status_code(result)
            if status >= 400:
                _tr.fail_task(task_id, f"generation returned HTTP {status}")
            else:
                _tr.complete_task(task_id)
        return result
    except Exception as exc:
        if task_id:
            _tr.fail_task(task_id, str(exc))
        raise


async def _handle_progress(_data: dict):
    task_id = _data.get("task_id") if isinstance(_data, dict) else None
    if task_id:
        from core.bridge_core.task_registry import get_progress_dict
        return api_success(get_progress_dict(task_id))

    from core.event_bus.event_types import GEN_PROGRESS
    try:
        client = _make_client()
    except Exception as exc:
        logger.warning("SD WebUI progress client init failed: %s", exc)
        return api_error("SD WebUI connection failed", 502)
    prog = client.get_progress()
    progress = prog.get("progress", 0)
    step = prog.get("state", {}).get("sampling_step", 0)
    total = prog.get("state", {}).get("sampling_steps", 0)
    if progress > 0:
        emit(
            GEN_PROGRESS,
            {"bridge": _BRIDGE_TAG, "progress": progress, "step": step, "total_steps": total},
            source=_EXT_NAME,
        )
    return api_success({
        "progress": progress,
        "step": step,
        "total_steps": total,
        "eta_relative": prog.get("eta_relative", 0),
    })


async def _handle_cancel(_data: dict):
    task_id = _data.get("task_id") if isinstance(_data, dict) else None
    if task_id:
        from core.bridge_core import task_registry as _tr
        task = _tr.get_task_entry(task_id)
        if task is None:
            return api_error("task not found", 404)
        ok = _tr.cancel_task(task_id)
        if not ok:
            return api_success({"cancelled": False, "message": "task not yet cancellable"})
        return api_success({"cancelled": True})

    try:
        client = _make_client()
    except Exception as exc:
        logger.warning("SD WebUI cancel client init failed: %s", exc)
        return api_error("SD WebUI connection failed", 502)
    ok = client.interrupt()
    if ok:
        emit(GEN_CANCEL, {"bridge": _BRIDGE_TAG}, source=_EXT_NAME)
        return api_success({"cancelled": True})
    return api_error("Cancel request failed", 502)


_register_generate(_BRIDGE_TAG, _handle_generate)
_register_progress(_BRIDGE_TAG, _handle_progress)
_register_cancel(_BRIDGE_TAG, _handle_cancel)


def create_sd_webui_bridge_blueprint(import_name: str) -> Blueprint:
    """Create and return the SD WebUI Bridge blueprint."""

    bp = Blueprint(
        "ext_sd_webui_bridge",
        import_name,
        template_folder="templates",
    )

    register_info_routes(
        bp,
        make_client=_make_client,
        get_api_url=_get_api_url,
        reset_client_cache=_reset_client_cache,
        ext_name=_EXT_NAME,
        bridge_tag=_BRIDGE_TAG,
        logger=logger,
    )
    register_model_routes(
        bp,
        make_client=_make_client,
        logger=logger,
    )
    register_config_routes(
        bp,
        require_admin_scope=_require_admin_scope,
        reset_client_cache=_reset_client_cache,
        ext_name=_EXT_NAME,
        save_naming_options=_SAVE_NAMING_OPTIONS,
        image_format_options=_IMAGE_FORMAT_OPTIONS,
        default_sampler_options=_DEFAULT_SAMPLER_OPTIONS,
    )

    @bp.route("/api/generate", methods=["POST"])
    async def api_generate():
        from core.infra_core.api_request import require_json_dict
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        assert data is not None
        return await _handle_generate(data)

    @bp.route("/api/save-batch", methods=["POST"])
    async def api_save_batch():
        from core.bridge_core.bridge_save import save_images
        from core.bridge_core.bridge_save_batch import handle_save_batch
        return await handle_save_batch(request, ext_name=_EXT_NAME, save_fn=save_images)

    register_sd_discovery_routes(bp, _make_client)

    from .sd_webui_api_diag_routes import register_diag_routes
    register_diag_routes(
        bp,
        require_admin_scope=_require_admin_scope,
        logger=logger,
    )
    return bp
