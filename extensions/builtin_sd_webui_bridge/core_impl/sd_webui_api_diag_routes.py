"""SD WebUI Bridge save-state diagnostic endpoint.

Exposes ``GET /api/save-state-diag`` so the bridge config UI can introspect
upstream ``samples_save`` / ``grid_save`` and ``/sdapi/v1/options``
reachability with one click. Mirrors the CLI ``scripts/check_sd_save_state.py``
so users do not need to drop to a shell to diagnose double-save issues.
"""
from __future__ import annotations

from typing import Any

from core.extensions_core.extensions_admin import get_extension_config_value

from core.bridge_core import (
    BridgeConnectionError,
    BridgeHTTPClient,
    BridgeHTTPError,
)
from core.infra_core.api_errors import api_error, api_success

_EXT_NAME = "builtin-sd-webui-bridge"


def _build_response(opts: dict[str, Any] | None, err: str | None,
                    api_url: str, bridge_managed: bool) -> dict[str, Any]:
    if opts is None:
        return {
            "api_url": api_url,
            "bridge_managed_save": bridge_managed,
            "options_reachable": False,
            "api_type_guess": "gradio4_or_disabled",
            "samples_save": None,
            "grid_save": None,
            "save_keys": [],
            "verdict": "options_unreachable",
            "verdict_message_key": (
                "sd_bridge.diag_save_state_verdict_options_unreachable"),
            "error": err,
        }
    samples_save = bool(opts.get("samples_save", True))
    grid_save = bool(opts.get("grid_save", True))
    save_keys = sorted(
        (
            {"key": k, "value": bool(opts[k])}
            for k in opts
            if "save" in k.lower() and isinstance(opts[k], bool)
        ),
        key=lambda d: d["key"],
    )
    if not samples_save and not grid_save:
        verdict = "ok"
        msg_key = "sd_bridge.diag_save_state_verdict_ok"
    else:
        verdict = "save_still_enabled"
        msg_key = "sd_bridge.diag_save_state_verdict_save_still_enabled"
    return {
        "api_url": api_url,
        "bridge_managed_save": bridge_managed,
        "options_reachable": True,
        "api_type_guess": "sdapi_v1",
        "samples_save": samples_save,
        "grid_save": grid_save,
        "save_keys": save_keys,
        "verdict": verdict,
        "verdict_message_key": msg_key,
        "error": None,
    }


def fetch_save_state(http: BridgeHTTPClient,
                     api_url: str,
                     bridge_managed: bool) -> dict[str, Any]:
    """Probe /sdapi/v1/options and shape the diagnostic payload."""
    try:
        opts = http.get("/sdapi/v1/options", timeout=10)
    except BridgeHTTPError as exc:
        return _build_response(
            None, f"HTTP {exc.status}", api_url, bridge_managed)
    except BridgeConnectionError as exc:
        return _build_response(
            None, f"connection error: {exc}", api_url, bridge_managed)
    if not isinstance(opts, dict):
        return _build_response(
            None, "non-dict response", api_url, bridge_managed)
    return _build_response(opts, None, api_url, bridge_managed)


def register_diag_routes(bp, *, require_admin_scope, logger) -> None:
    @bp.route("/api/save-state-diag", methods=["GET"])
    async def api_save_state_diag():
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        api_url = get_extension_config_value(
            _EXT_NAME, "api_url", "http://127.0.0.1:7860")
        bridge_managed = bool(get_extension_config_value(
            _EXT_NAME, "bridge_managed_save", False))
        try:
            from .sd_webui_api import _get_default_headers
            http = BridgeHTTPClient(api_url, timeout=10.0,
                                    default_headers=_get_default_headers())
            payload = fetch_save_state(http, api_url, bridge_managed)
        except Exception:
            logger.exception("save-state-diag failed unexpectedly")
            return api_error("save-state-diag failed", 502)
        return api_success(payload)
