"""Headroom proxy API — /livez, /readyz, /health, /stats, /stats-history, /metrics, and config GET/PUT."""

from __future__ import annotations

import json
import logging

import httpx
from quart import Blueprint, Response, current_app, request, session  # session: browser fallback

from core.gateway.headroom_proxy import configure as _configure_proxy
from core.gateway.headroom_proxy import configure_auth_key as _configure_auth_key
from core.gateway.headroom_proxy import get_upstream_base_url
from core.gateway.headroom_proxy import validate_base_url as _validate_base_url
from core.gateway.scopes import Scope
from core.infra_core.api_errors import api_result

logger = logging.getLogger(__name__)

bp = Blueprint("headroom_api", __name__)
bp_config = Blueprint("headroom_config", __name__, url_prefix="/api/gateway")

_TIMEOUT = 5.0
_DEFAULT_BASE_URL = "http://127.0.0.1:8787"


def _auth(required: Scope) -> tuple[Response, int] | None:
    """Auth check for headroom endpoints.

    Bearer token present → gateway-auth scope check (always enforced).
    No Bearer token       → browser-session fallback (PIN or no-PIN-auth).
    """
    from core.gateway.auth import extract_bearer, get_auth
    from core.gateway.errors import openai_error
    bearer = extract_bearer(
        request.headers.get("Authorization"),
        request.headers.get("x-api-key"),
    )
    if bearer is not None:
        auth = get_auth()
        result = auth.check_request(
            bearer=bearer,
            remote_addr=request.remote_addr or "",
            allow_loopback_bypass=False,  # bearer present: always enforce scope
        )
        if result is None:
            return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
        if not auth.has_scope(result, required):
            return openai_error("Insufficient scope", "insufficient_scope", 403, param=str(required))
        return None
    # No Bearer: browser session fallback
    if current_app.config.get("PIN_AUTH") and not session.get("pin_ok"):
        return Response('{"error":"Unauthorized"}', status=401, content_type="application/json"), 401
    return None


async def _fetch(path: str) -> tuple[dict, int]:
    base = get_upstream_base_url()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{base}{path}")
            try:
                data = resp.json()
            except Exception:
                data = {}
            return data, resp.status_code
    except httpx.ConnectError:
        return {"error": "headroom not reachable", "code": "offline"}, 503
    except httpx.TimeoutException:
        return {"error": "headroom timed out", "code": "timeout"}, 504
    except Exception:
        return {"error": "headroom request failed", "code": "error"}, 502


@bp.route("/api/headroom/livez")
async def headroom_livez() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    data, status = await _fetch("/livez")
    return api_result(data, status)


@bp.route("/api/headroom/readyz")
async def headroom_readyz() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    data, status = await _fetch("/readyz")
    return api_result(data, status)


@bp.route("/api/headroom/health")
async def headroom_health() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    data, status = await _fetch("/health")
    return api_result(data, status)


@bp.route("/api/headroom/stats")
async def headroom_stats() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    data, status = await _fetch("/stats")
    return api_result(data, status)


@bp.route("/api/headroom/stats-history")
async def headroom_stats_history() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    qs = request.query_string.decode()
    path = f"/stats-history{'?' + qs if qs else ''}"
    data, status = await _fetch(path)
    return api_result(data, status)


@bp.route("/api/headroom/metrics")
async def headroom_metrics() -> Response:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    data, status = await _fetch("/metrics")
    return api_result(data, status)


# ---------------------------------------------------------------------------
# Config API  (GET/PUT /api/gateway/headroom/config)
# ---------------------------------------------------------------------------

@bp_config.route("/headroom/config", methods=["GET"])
async def get_headroom_config() -> tuple[Response, int]:
    err = _auth(Scope.HEADROOM_READ)
    if err:
        return err
    from core.configuration.json_rw import load_config_json
    cfg = load_config_json()
    hr_cfg = cfg.get("gateway", {}).get("backends", {}).get("headroom", {})
    stored_url = hr_cfg.get("base_url", _DEFAULT_BASE_URL)
    try:
        _validate_base_url(stored_url)
        base_url = stored_url
        response_data = {"base_url": base_url, "auth_key_configured": bool(hr_cfg.get("auth_key"))}
    except (TypeError, ValueError):
        base_url = _DEFAULT_BASE_URL
        response_data = {
            "base_url": base_url,
            "auth_key_configured": bool(hr_cfg.get("auth_key")),
            "config_status": "invalid",
        }
    return Response(
        json.dumps(response_data),
        content_type="application/json",
    ), 200


@bp_config.route("/headroom/config", methods=["PUT"])
async def put_headroom_config() -> tuple[Response, int]:
    err = _auth(Scope.HEADROOM_ADMIN)
    if err:
        return err
    body = await request.get_json() or {}
    new_url = (body.get("base_url") or "").strip().rstrip("/")
    try:
        _validate_base_url(new_url)
    except ValueError as exc:
        return Response(json.dumps({"error": str(exc)}), status=400, content_type="application/json"), 400
    from core.configuration.json_rw import load_config_json, save_config_json
    from core.settings_core.secret_store import decrypt, encrypt
    cfg = load_config_json()
    hr = cfg.setdefault("gateway", {}).setdefault("backends", {}).setdefault("headroom", {})
    hr["base_url"] = new_url
    if "auth_key" in body:
        new_auth_key = str(body.get("auth_key") or "").strip()
    else:
        new_auth_key = decrypt(str(hr.get("auth_key") or ""))
    hr["auth_key"] = encrypt(new_auth_key)
    save_config_json(cfg)
    _configure_proxy(new_url)
    _configure_auth_key(new_auth_key)
    logger.info("[gateway:headroom] base_url updated")
    return Response(json.dumps({"base_url": new_url, "auth_key_configured": bool(new_auth_key)}), content_type="application/json"), 200
