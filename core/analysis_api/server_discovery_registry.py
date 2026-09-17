"""Registration and probe flows for discovered AI servers."""

from __future__ import annotations

import time

from core.infra_core.api_request import validate_json_model
from core.llm_endpoint_discovery.probes import normalize_base_url
from core.settings_core.secret_store import decrypt

from .server_discovery_match import (
    _cleanup_discovery_metadata,
    _load_discovery_ignored,
    _load_discovery_matches,
)
from .server_discovery_request_models import (
    RegisterDiscoveredCandidateRequest,
    TestDiscoveredCandidateRequest,
)
from .server_model_data import _validate_and_build
from .server_model_resolve import _is_ollama_available


def _next_low_priority(servers: list[dict]) -> int:
    if not servers:
        return 10
    return max(int(s.get("priority", 0)) for s in servers) + 10


def _resolve_openai_compat_secret(config: dict, data: dict, base_url: str) -> tuple[str, str]:
    explicit_key = (data.get("api_key") or "").strip()
    if explicit_key:
        return explicit_key, explicit_key

    servers = config.get("ai_servers", [])
    if isinstance(servers, list):
        for server in servers:
            if not isinstance(server, dict):
                continue
            server_cfg = server.get("config", {})
            if not isinstance(server_cfg, dict):
                continue
            if normalize_base_url(server_cfg.get("base_url", "")) != base_url:
                continue
            raw_key = server_cfg.get("api_key", "")
            if raw_key:
                return decrypt(raw_key), raw_key

    ai_cfg = config.get("ai_analysis") or {}
    configured_base = normalize_base_url(ai_cfg.get("openai_compat_url", ""))
    if configured_base == base_url:
        raw_key = ai_cfg.get("openai_compat_api_key", "")
        if raw_key:
            return decrypt(raw_key), raw_key
    return "", ""


def register_discovered_candidate(data: dict) -> dict:
    validated, err = validate_json_model(RegisterDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    config = facade.load_config_json(None)
    servers = config.get("ai_servers", [])
    if not isinstance(servers, list):
        servers = []

    base_url = normalize_base_url((data.get("base_url") or "").strip())
    provider = (data.get("provider") or "").strip()
    if not base_url:
        return {"success": False, "error": "base_url is required"}

    existing_urls = {
        normalize_base_url(s.get("config", {}).get("base_url", ""))
        for s in servers
        if isinstance(s, dict)
    }
    if provider == "ollama":
        if base_url in existing_urls:
            return {"success": False, "error": "Server already registered"}
        host_label = base_url.split("://", 1)[-1]
        entry = _validate_and_build({
            "name": (data.get("name") or f"Ollama ({host_label})").strip(),
            "type": "ollama",
            "priority": _next_low_priority(servers),
            "enabled": True,
            "config": {
                "base_url": base_url,
                "model": (data.get("model") or "llava:latest").strip(),
            },
        }, servers)
    elif provider == "openai_compat":
        if base_url in existing_urls:
            return {"success": False, "error": "Server already registered"}
        model = (data.get("model") or "").strip()
        api_key, stored_api_key = _resolve_openai_compat_secret(config, data, base_url)
        host_label = base_url.split("://", 1)[-1]
        compat_config: dict = {
            "base_url": base_url,
            "model": model,
        }
        if stored_api_key:
            compat_config["api_key"] = stored_api_key
        entry = _validate_and_build({
            "name": (data.get("name") or f"OpenAI Compatible ({host_label})").strip(),
            "type": "openai_compat",
            "priority": _next_low_priority(servers),
            "enabled": True,
            "config": compat_config,
        }, servers)
    elif provider == "hailo_genai":
        if any((s.get("type") == "hailo_vlm") for s in servers if isinstance(s, dict)):
            return {"success": False, "error": "Server already registered"}
        model_name = (data.get("model_name") or "qwen2-vl-2b-instruct").strip()
        entry = _validate_and_build({
            "name": (data.get("name") or f"Hailo VLM ({model_name})").strip(),
            "type": "hailo_vlm",
            "priority": _next_low_priority(servers),
            "enabled": True,
            "config": {
                "model_name": model_name,
            },
        }, servers)
    else:
        return {"success": False, "error": f"Unsupported provider for v1: {provider}"}

    if isinstance(entry, dict):
        return entry

    servers.append(entry.to_dict())
    config["ai_servers"] = servers
    _cleanup_discovery_metadata(config)
    base_match_key = normalize_base_url(base_url)
    matches = _load_discovery_matches(config)
    if base_match_key in matches:
        matches.pop(base_match_key, None)
        if matches:
            config["ai_servers_discovery_matches"] = matches
        else:
            config.pop("ai_servers_discovery_matches", None)
    ignored = _load_discovery_ignored(config)
    if base_match_key in ignored:
        ignored.discard(base_match_key)
        if ignored:
            config["ai_servers_discovery_ignored"] = sorted(ignored)
        else:
            config.pop("ai_servers_discovery_ignored", None)
    facade.save_config_json(config, "config.json")
    return {"success": True, "server": entry.to_dict()}


def run_discovered_candidate_test(data: dict) -> dict:
    validated, err = validate_json_model(TestDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    provider = (data.get("provider") or "").strip()
    base_url = normalize_base_url((data.get("base_url") or "").strip())
    start = time.time()

    if provider == "ollama":
        if not base_url:
            return {"success": False, "error": "base_url is required"}
        available = _is_ollama_available(base_url)
    elif provider == "openai_compat":
        if not base_url:
            return {"success": False, "error": "base_url is required"}
        config = facade.load_config_json(None)
        api_key, _stored_api_key = _resolve_openai_compat_secret(config, data, base_url)
        available, reason = facade.probe_openai_compat_models(base_url, api_key=api_key, timeout=3.0)
        if not available and reason == "auth_required":
            return {"success": True, "available": False, "auth_required": True, "elapsed_ms": int((time.time() - start) * 1000)}
    elif provider == "hailo_genai":
        model_name = (data.get("model_name") or "qwen2-vl-2b-instruct").strip()
        available = facade._is_hailo_vlm_available(model_name)
    else:
        return {"success": False, "error": f"Unsupported provider for v1: {provider}"}

    elapsed_ms = int((time.time() - start) * 1000)
    return {"success": True, "available": available, "elapsed_ms": elapsed_ms}
