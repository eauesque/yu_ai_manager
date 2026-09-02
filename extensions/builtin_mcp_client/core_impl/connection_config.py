"""Connection configuration CRUD for MCP client.

Settings are persisted inside ``config.json`` under
``extensions.builtin_mcp_client.connections`` via the standard
extension config API.
"""

from __future__ import annotations

import json as _json
import logging
import uuid

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

from core.settings_core.secret_store import decrypt as _decrypt
from core.settings_core.secret_store import encrypt as _encrypt
from core.settings_core.secret_store import is_encrypted as _is_encrypted

logger = logging.getLogger(__name__)

EXT_NAME = "builtin-mcp-client"
_CONNECTIONS_KEY = "connections"

# ── schema helpers ──────────────────────────────────────────────────

_REQUIRED_FIELDS = {"name", "transport"}
_TRANSPORTS = {"stdio", "sse", "streamable_http"}


def _encrypt_sensitive(cfg: dict) -> dict:
    """Encrypt headers/env dicts in a connection config before saving."""
    cfg = dict(cfg)
    for key in ("sse", "streamable_http"):
        if key in cfg:
            tc = dict(cfg[key])
            headers = tc.get("headers")
            if headers and isinstance(headers, dict):
                tc["headers"] = _encrypt(_json.dumps(headers))
                cfg[key] = tc
    if "stdio" in cfg:
        sc = dict(cfg["stdio"])
        env = sc.get("env")
        if env and isinstance(env, dict):
            sc["env"] = _encrypt(_json.dumps(env))
            cfg["stdio"] = sc
    return cfg


def _decrypt_sensitive(cfg: dict) -> dict:
    """Decrypt headers/env dicts in a connection config after loading."""
    cfg = dict(cfg)
    conn_id = str(cfg.get("id") or "<unknown>")
    for key in ("sse", "streamable_http"):
        if key in cfg:
            tc = dict(cfg[key])
            headers = tc.get("headers")
            if isinstance(headers, str) and _is_encrypted(headers):
                try:
                    tc["headers"] = _json.loads(_decrypt(headers))
                except Exception as exc:
                    logger.warning(
                        "Failed to decrypt MCP %s headers for connection %s: %s",
                        key,
                        conn_id,
                        exc,
                    )
                    tc["headers"] = {}
                cfg[key] = tc
    if "stdio" in cfg:
        sc = dict(cfg["stdio"])
        env = sc.get("env")
        if isinstance(env, str) and _is_encrypted(env):
            try:
                sc["env"] = _json.loads(_decrypt(env))
            except Exception as exc:
                logger.warning(
                    "Failed to decrypt MCP stdio env for connection %s: %s",
                    conn_id,
                    exc,
                )
                sc["env"] = {}
            cfg["stdio"] = sc
    return cfg


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _validate(cfg: dict) -> str | None:
    """Return an error string or None."""
    missing = _REQUIRED_FIELDS - set(cfg)
    if missing:
        return f"Missing required fields: {', '.join(sorted(missing))}"
    if cfg["transport"] not in _TRANSPORTS:
        return f"Invalid transport: {cfg['transport']}. Must be one of {_TRANSPORTS}"
    if cfg["transport"] == "stdio":
        stdio = cfg.get("stdio", {})
        if not stdio.get("command"):
            return "stdio.command is required for stdio transport"
    elif cfg["transport"] == "sse":
        if not cfg.get("sse", {}).get("url"):
            return "sse.url is required for sse transport"
    elif cfg["transport"] == "streamable_http":
        if not cfg.get("streamable_http", {}).get("url"):
            return "streamable_http.url is required for streamable_http transport"
    return None


# ── CRUD ────────────────────────────────────────────────────────────

def list_connections() -> list[dict]:
    """Return decrypted connections (for runtime use)."""
    raw = get_extension_config_value(EXT_NAME, _CONNECTIONS_KEY, [])
    return [_decrypt_sensitive(c) for c in raw]


def get_connection(conn_id: str) -> dict | None:
    for c in list_connections():
        if c.get("id") == conn_id:
            return c
    return None


def add_connection(cfg: dict) -> tuple[dict | None, str | None]:
    """Add a new connection. Returns (saved_config, error)."""
    err = _validate(cfg)
    if err:
        return None, err
    cfg.setdefault("id", _new_id())
    cfg.setdefault("enabled", True)
    cfg.setdefault("auto_connect", False)
    raw = get_extension_config_value(EXT_NAME, _CONNECTIONS_KEY, [])
    if any(c.get("id") == cfg["id"] for c in raw):
        return None, f"Connection ID already exists: {cfg['id']}"
    raw.append(_encrypt_sensitive(cfg))
    save_extension_config_values(EXT_NAME, {_CONNECTIONS_KEY: raw})
    return cfg, None


def update_connection(conn_id: str, updates: dict) -> tuple[dict | None, str | None]:
    """Update an existing connection. Returns (updated, error)."""
    raw = get_extension_config_value(EXT_NAME, _CONNECTIONS_KEY, [])
    for i, c in enumerate(raw):
        if c.get("id") == conn_id:
            decrypted = _decrypt_sensitive(c)
            decrypted.update(updates)
            decrypted["id"] = conn_id  # prevent id change
            err = _validate(decrypted)
            if err:
                return None, err
            raw[i] = _encrypt_sensitive(decrypted)
            save_extension_config_values(EXT_NAME, {_CONNECTIONS_KEY: raw})
            return decrypted, None
    return None, f"Connection not found: {conn_id}"


def delete_connection(conn_id: str) -> str | None:
    """Delete a connection. Returns error string or None."""
    raw = get_extension_config_value(EXT_NAME, _CONNECTIONS_KEY, [])
    new = [c for c in raw if c.get("id") != conn_id]
    if len(new) == len(raw):
        return f"Connection not found: {conn_id}"
    save_extension_config_values(EXT_NAME, {_CONNECTIONS_KEY: new})
    return None
