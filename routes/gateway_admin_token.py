"""Admin token provisioning endpoint.

Only accessible from loopback. DNS rebinding protected via Host header check.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from urllib.parse import urlparse

from quart import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
bp = Blueprint("gateway_admin_token", __name__, url_prefix="/api/gateway")

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ADMIN_KEY_CONFIG_NAME = "gateway_admin_key"
_ADMIN_KEY_ID = "gateway_admin"
_key_lock: asyncio.Lock | None = None


def _get_key_lock() -> asyncio.Lock:
    global _key_lock
    if _key_lock is None:
        _key_lock = asyncio.Lock()
    return _key_lock


def _get_or_create_admin_key() -> str:
    from core.configuration.json_rw import load_config_json, save_config_json
    from core.gateway.auth import get_auth
    from core.gateway.scopes import Scope
    from core.settings_core.secret_store import decrypt, encrypt

    cfg = load_config_json()
    gateway_cfg = cfg.setdefault("gateway", {})
    stored_key = gateway_cfg.get(_ADMIN_KEY_CONFIG_NAME, "")
    key = decrypt(stored_key) if stored_key else ""

    if stored_key and not key:
        logger.error("admin-token: failed to decrypt stored gateway_admin_key; regenerating a new one")

    if not key:
        key = secrets.token_hex(32)
        gateway_cfg[_ADMIN_KEY_CONFIG_NAME] = encrypt(key)
        save_config_json(cfg)

    auth = get_auth()
    # Always re-register using direct digest - bypasses encrypt/decrypt entirely
    # so keyring issues cannot prevent the admin key from being recognized.
    digest = hashlib.sha256(key.encode()).digest()
    auth.add_key_by_digest(
        key_id=_ADMIN_KEY_ID,
        digest=digest,
        scopes=[str(Scope.GATEWAY_ADMIN)],
        allowed_models=None,
    )
    return key


@bp.route("/admin-token", methods=["GET"])
async def get_admin_token():
    remote = request.remote_addr or ""
    raw_host = request.headers.get("Host", "")
    host_header = raw_host.split("]")[0].lstrip("[") if raw_host.startswith("[") else raw_host.split(":")[0]

    if remote not in _LOOPBACK_HOSTS:
        return jsonify({"error": "Forbidden"}), 403

    if host_header and host_header not in _LOOPBACK_HOSTS:
        logger.warning("admin-token: suspicious Host header %s from %s", host_header, remote)
        return jsonify({"error": "Forbidden"}), 403

    origin = request.headers.get("Origin", "")
    if origin:
        origin_url = urlparse(origin)
        if not origin_url.hostname or origin_url.hostname not in _LOOPBACK_HOSTS:
            return jsonify({"error": "Forbidden"}), 403

    async with _get_key_lock():
        key = _get_or_create_admin_key()
    resp = jsonify({"token": key})
    resp.headers["Cache-Control"] = "no-store"
    return resp
