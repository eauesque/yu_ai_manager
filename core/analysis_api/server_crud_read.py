"""Read-only helpers for AI server CRUD."""

from __future__ import annotations

import time

from core.configuration.api import load_config_json

from .server_model_data import get_active_server_id, get_all_servers
from .server_model_resolve import _check_available


def test_server(server_id: str) -> dict:
    """Run a connectivity test on a server."""
    config = load_config_json(None)
    servers = get_all_servers(config)

    for server in servers:
        if server.id == server_id:
            start = time.time()
            available = _check_available(server)
            elapsed_ms = int((time.time() - start) * 1000)
            return {
                "success": True,
                "available": available,
                "elapsed_ms": elapsed_ms,
                "server": server.to_dict(),
            }

    return {"success": False, "error": f"Server '{server_id}' not found"}


def get_servers_with_status(config: dict | None = None) -> list[dict]:
    """Return all servers with masked config and passive status."""
    servers = get_all_servers(config)
    active_id = get_active_server_id(config)
    result = []
    for server in servers:
        data = server.to_dict()
        data["is_active"] = server.id == active_id
        data["status"] = "unknown"
        cfg = data.get("config", {})
        for key in ("api_key",):
            if cfg.get(key) and len(cfg[key]) > 6:
                cfg[key] = cfg[key][:4] + "..." + cfg[key][-2:]
        result.append(data)
    return result
