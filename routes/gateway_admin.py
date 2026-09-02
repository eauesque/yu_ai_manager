from __future__ import annotations

import json
import logging
import secrets

from quart import Blueprint, Response, g, request

from core.gateway.auth import GatewayAuth, get_auth
from core.gateway.errors import openai_error
from core.gateway.scopes import Scope
from core.settings_core.secret_store import encrypt

bp = Blueprint("gateway_admin", __name__, url_prefix="/api/gateway")
logger = logging.getLogger(__name__)

_auth_override: GatewayAuth | None = None


def set_auth_override(auth: GatewayAuth) -> None:
    global _auth_override
    _auth_override = auth


def _get_auth() -> GatewayAuth:
    return _auth_override if _auth_override is not None else get_auth()


def _require_admin_bearer() -> Response | None:
    """Bearer * scope only. No session fallback.
    Used for machine-to-machine endpoints (/auth/reload) that should
    never be reachable via browser session even for local users.
    """
    auth = _get_auth()
    h = request.headers.get("Authorization", "")
    bearer = h[len("Bearer "):] if h.startswith("Bearer ") else \
             request.headers.get("x-api-key") or None
    result = auth.check_bearer(bearer, remote_addr=request.remote_addr or "")
    if result is None:
        return openai_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not auth.has_scope(result, Scope.WILDCARD):
        return openai_error("Requires * scope", "insufficient_scope", 403)
    g.gateway_auth_path = "bearer"
    return None


def _require_admin_or_session() -> Response | None:
    """Bearer * を試み、なければ Webセッション(require_pin)。WebUI経由エンドポイント専用。"""
    from core.web.auth_helpers import require_pin
    auth = _get_auth()
    h = request.headers.get("Authorization", "")
    bearer = h[len("Bearer "):] if h.startswith("Bearer ") else \
             request.headers.get("x-api-key") or None
    if bearer:
        result = auth.check_bearer(bearer, remote_addr=request.remote_addr or "")
        if result is not None and auth.has_scope(result, Scope.WILDCARD):
            g.gateway_auth_path = "bearer"
            return None
    err = require_pin()
    if err:
        return err
    g.gateway_auth_path = "session"
    return None


def _persist_keys(auth: GatewayAuth) -> None:
    try:
        from core.configuration.json_rw import load_config_json, save_config_json
        cfg = load_config_json()
        gw_auth = cfg.setdefault("gateway", {}).setdefault("auth", {})
        new_entries = list(auth.iter_persistable_keys())
        gw_auth["api_keys"] = new_entries
        save_config_json(cfg)
    except Exception as exc:
        logger.warning("[gateway:admin] persist failed: %s", exc)


def _emit_admin_event(event: str, key_id: str, scopes: list[str]) -> None:
    from datetime import UTC, datetime

    from core.gateway.audit import AdminAuditRecord, get_writer

    writer = get_writer()
    if writer is None:
        return
    writer.emit_admin(AdminAuditRecord(
        event=event,
        key_id=key_id,
        scopes=scopes,
        auth_path=g.get("gateway_auth_path", "unknown"),
        client_ip=request.remote_addr or "",
        timestamp=datetime.now(UTC),
    ))


@bp.route("/keys", methods=["POST"])
async def create_key():
    err = _require_admin_or_session()
    if err:
        return err
    body = await request.get_json() or {}
    key_id = body.get("id", "")
    if not key_id:
        return openai_error("id is required", "invalid_request_error", 400)
    auth = _get_auth()
    if auth.has_key(key_id):
        return openai_error(f"Key id '{key_id}' already exists", "invalid_request_error", 409)
    plain = secrets.token_urlsafe(32)
    secret_enc = encrypt(plain)
    auth.add_key(key_id, secret_enc, body.get("scopes", []), body.get("allowed_models"))
    _persist_keys(auth)
    _emit_admin_event("gateway_key.created", key_id, body.get("scopes", []))
    return Response(
        json.dumps({"id": key_id, "scopes": body.get("scopes", []), "secret": plain},
                   ensure_ascii=False),
        content_type="application/json",
    )


@bp.route("/keys", methods=["GET"])
async def list_keys():
    err = _require_admin_or_session()
    if err:
        return err
    return Response(
        json.dumps({"keys": _get_auth().list_keys()}, ensure_ascii=False),
        content_type="application/json",
    )


@bp.route("/keys/<key_id>", methods=["DELETE"])
async def delete_key(key_id: str):
    err = _require_admin_or_session()
    if err:
        return err
    auth = _get_auth()
    # capture scopes before deletion for audit log
    scopes_snapshot = auth.get_key_scopes(key_id) or []
    # last * key guard
    wildcard_ids = auth.wildcard_key_ids()
    if key_id in wildcard_ids and len(wildcard_ids) == 1:
        return openai_error(
            "Cannot delete the last key with * scope",
            "invalid_request_error", 409
        )
    if not auth.remove_key(key_id):
        return openai_error(f"Key {key_id!r} not found", "invalid_request_error", 404)
    _persist_keys(auth)
    _emit_admin_event("gateway_key.deleted", key_id, scopes_snapshot)
    return Response(json.dumps({"deleted": key_id}), content_type="application/json")


@bp.route("/keys/<key_id>", methods=["PATCH"])
async def patch_key(key_id: str):
    err = _require_admin_bearer()
    if err:
        return err
    body = await request.get_json() or {}
    auth = _get_auth()
    if not auth.patch_key(key_id, body.get("scopes"), body.get("allowed_models")):
        return openai_error(f"Key {key_id!r} not found", "invalid_request_error", 404)
    _persist_keys(auth)
    return Response(json.dumps({"id": key_id}), content_type="application/json")


@bp.route("/auth/reload", methods=["POST"])
async def reload_auth():
    err = _require_admin_bearer()
    if err:
        return err
    try:
        from core.configuration.json_rw import load_config_json
        from core.gateway.auth import load_config_from_app_config
        cfg = load_config_json()
        _get_auth().load_config(load_config_from_app_config(cfg))
    except Exception:
        logger.exception("[gateway:admin] auth reload failed")
        return openai_error("reload failed", "server_error", 500)
    return Response(json.dumps({"reloaded": True}), content_type="application/json")
