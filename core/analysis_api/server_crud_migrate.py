"""Legacy migration helpers for AI server CRUD."""

from __future__ import annotations

from core.configuration.api import load_config_json, save_config_json

from .server_model_data import _legacy_to_entry, _slugify, has_servers


def migrate_from_legacy(config: dict | None = None) -> dict:
    """Auto-generate server entries from legacy ai_analysis config."""
    if config is None:
        config = load_config_json(None)

    if has_servers(config):
        return {"success": False, "error": "ai_servers already exists"}

    ai = config.get("ai_analysis", {})
    servers: list[dict] = []
    priority = 10

    main = _legacy_to_entry(ai)
    if main:
        main.id = _slugify(main.name)
        main.priority = priority
        servers.append(main.to_dict())
        priority += 10

    main_type = ai.get("engine", "claude_api")

    if main_type != "openai_compat" and ai.get("openai_compat_url"):
        servers.append({
            "id": "openai-compat",
            "name": f'OpenAI Compatible ({ai.get("openai_compat_model", "default")})',
            "type": "openai_compat",
            "priority": priority,
            "enabled": True,
            "config": {
                "base_url": ai.get("openai_compat_url", ""),
                "api_key": ai.get("openai_compat_api_key", ""),
                "model": ai.get("openai_compat_model", ""),
            },
        })
        priority += 10

    if main_type != "ollama" and ai.get("ollama_url"):
        servers.append({
            "id": "ollama",
            "name": f'Ollama ({ai.get("ollama_model", "llava:latest")})',
            "type": "ollama",
            "priority": priority,
            "enabled": True,
            "config": {
                "base_url": ai.get("ollama_url", "http://localhost:11434"),
                "model": ai.get("ollama_model", "llava:latest"),
            },
        })
        priority += 10

    if main_type != "hailo_vlm":
        servers.append({
            "id": "hailo-vlm",
            "name": f'Hailo VLM ({ai.get("hailo_vlm_model", "qwen2-vl-2b-instruct")})',
            "type": "hailo_vlm",
            "priority": priority,
            "enabled": True,
            "config": {
                "model_name": ai.get("hailo_vlm_model", "qwen2-vl-2b-instruct"),
            },
        })

    config["ai_servers"] = servers
    if servers:
        config["ai_servers_active"] = servers[0]["id"]
    if ai.get("language"):
        config["ai_servers_language"] = ai["language"]
    if "fallback_local_only" in ai:
        config["ai_servers_fallback_local_only"] = ai["fallback_local_only"]

    save_config_json(config, "config.json")
    return {"success": True, "servers": servers, "migrated": len(servers)}
