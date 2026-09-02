"""AI server CRUD operations, testing, and legacy migration."""

from __future__ import annotations

from core.configuration.api import load_config_json, save_config_json
from core.infra_core.api_request import validate_json_model

from .server_api_models import AnalysisServerCreateRequest, AnalysisServerUpdateRequest
from .server_crud_migrate import migrate_from_legacy  # noqa: F401
from .server_crud_read import get_servers_with_status, test_server  # noqa: F401
from .server_discovery import _cleanup_discovery_metadata
from .server_model_data import (
    _MAX_SERVERS,
    VALID_TYPES,
    _legacy_to_entry,
    _validate_and_build,
)


def add_server(data: dict) -> dict:
    """Add a new server entry."""
    validated, err = validate_json_model(AnalysisServerCreateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}

    config = load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        servers = []

    if len(servers) >= _MAX_SERVERS:
        return {"success": False, "error": f"Maximum {_MAX_SERVERS} servers allowed"}

    assert validated is not None
    entry = _validate_and_build(validated.model_dump(exclude_none=True), servers)
    if isinstance(entry, dict):
        return entry

    servers.append(entry.to_dict())
    config["ai_servers"] = servers
    if not config.get("ai_servers_active"):
        config["ai_servers_active"] = entry.id

    save_config_json(config, "config.json")
    return {"success": True, "server": entry.to_dict()}


def update_server(server_id: str, data: dict) -> dict:
    """Update an existing server's settings."""
    validated, err = validate_json_model(AnalysisServerUpdateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    config = load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        return {"success": False, "error": "No servers configured"}

    for i, server in enumerate(servers):
        if server.get("id") == server_id:
            if "name" in data:
                server["name"] = data["name"]
            if "type" in data:
                if data["type"] not in VALID_TYPES:
                    return {"success": False, "error": f"Invalid type: {data['type']}"}
                server["type"] = data["type"]
            if "priority" in data:
                server["priority"] = int(data["priority"])
            if "enabled" in data:
                if not isinstance(data["enabled"], bool):
                    return {"success": False, "error": "enabled must be a boolean"}
                server["enabled"] = data["enabled"]
            if "config" in data:
                server["config"] = data["config"]
            servers[i] = server
            config["ai_servers"] = servers
            _cleanup_discovery_metadata(config)
            save_config_json(config, "config.json")
            return {"success": True, "server": server}

    if server_id == "legacy-default":
        legacy = _legacy_to_entry(config.get("ai_analysis", {}))
        if legacy:
            entry = legacy.to_dict()
            if "name" in data:
                entry["name"] = data["name"]
            if "type" in data:
                if data["type"] not in VALID_TYPES:
                    return {"success": False, "error": f"Invalid type: {data['type']}"}
                entry["type"] = data["type"]
            if "priority" in data:
                entry["priority"] = int(data["priority"])
            if "enabled" in data:
                if not isinstance(data["enabled"], bool):
                    return {"success": False, "error": "enabled must be a boolean"}
                entry["enabled"] = data["enabled"]
            if "config" in data:
                entry["config"] = data["config"]
            servers.append(entry)
            config["ai_servers"] = servers
            if not config.get("ai_servers_active"):
                config["ai_servers_active"] = "legacy-default"
            _cleanup_discovery_metadata(config)
            save_config_json(config, "config.json")
            return {"success": True, "server": entry}

    return {"success": False, "error": f"Server '{server_id}' not found"}


def remove_server(server_id: str) -> dict:
    """Remove a server entry."""
    config = load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        return {"success": False, "error": "No servers configured"}

    new_servers = [server for server in servers if server.get("id") != server_id]
    if len(new_servers) == len(servers):
        return {"success": False, "error": f"Server '{server_id}' not found"}

    config["ai_servers"] = new_servers
    if config.get("ai_servers_active") == server_id:
        if new_servers:
            sorted_servers = sorted(
                new_servers,
                key=lambda server: server.get("priority", 50),
            )
            config["ai_servers_active"] = sorted_servers[0].get("id")
        else:
            config.pop("ai_servers_active", None)

    _cleanup_discovery_metadata(config)
    save_config_json(config, "config.json")
    return {"success": True}


def set_active_server(server_id: str) -> dict:
    """Switch the active server."""
    config = load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        return {"success": False, "error": "No servers configured"}

    if not any(server.get("id") == server_id for server in servers):
        return {"success": False, "error": f"Server '{server_id}' not found"}

    config["ai_servers_active"] = server_id
    save_config_json(config, "config.json")
    return {"success": True, "active": server_id}


def reorder_servers(server_ids: list[str]) -> dict:
    """Bulk-update server priorities based on the given order."""
    config = load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        return {"success": False, "error": "No servers configured"}

    id_map = {server.get("id"): server for server in servers}
    for idx, server_id in enumerate(server_ids):
        if server_id in id_map:
            id_map[server_id]["priority"] = (idx + 1) * 10

    config["ai_servers"] = list(id_map.values())
    save_config_json(config, "config.json")
    return {"success": True}
