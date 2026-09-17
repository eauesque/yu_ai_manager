"""Matching and ignore-state helpers for discovered AI servers."""

from __future__ import annotations

import time

from core.infra_core.api_request import validate_json_model
from core.llm_endpoint_discovery.probes import normalize_base_url

from .server_discovery_request_models import (
    IgnoreDiscoveredCandidateRequest,
    MatchDiscoveredCandidateRequest,
)
from .server_model_data import ServerEntry, get_all_servers


def _load_discovery_matches(config: dict) -> dict[str, dict]:
    raw = config.get("ai_servers_discovery_matches")
    return raw if isinstance(raw, dict) else {}


def _load_discovery_ignored(config: dict) -> set[str]:
    raw = config.get("ai_servers_discovery_ignored")
    if not isinstance(raw, list):
        return set()
    return {normalize_base_url(str(item or "")) for item in raw if str(item or "").strip()}


def _compatible_server_types(provider: str) -> set[str]:
    if provider == "ollama":
        return {"ollama"}
    if provider == "openai_compat":
        return {"openai_compat"}
    if provider == "hailo_genai":
        return {"hailo_vlm"}
    return set()


def _build_match_state(
    provider: str,
    canonical_url: str,
    servers: list[ServerEntry],
    config: dict,
) -> tuple[list[dict], str | None, str | None]:
    compatible = _compatible_server_types(provider)
    matchable_servers = [{"id": s.id, "name": s.name} for s in servers if s.type in compatible]
    matches = _load_discovery_matches(config)
    raw_match = matches.get(canonical_url)
    if not isinstance(raw_match, dict):
        return matchable_servers, None, None
    server_id = raw_match.get("server_id")
    matched = next((s for s in servers if s.id == server_id and s.type in compatible), None)
    if not matched:
        return matchable_servers, None, None
    return matchable_servers, matched.id, matched.name


def _cleanup_discovery_metadata(config: dict) -> None:
    raw_servers = config.get("ai_servers", [])
    if not isinstance(raw_servers, list):
        raw_servers = []
    server_map = {
        str(s.get("id")): s
        for s in raw_servers
        if isinstance(s, dict) and s.get("id")
    }
    matches = _load_discovery_matches(config)
    cleaned_matches = {
        canonical_url: data
        for canonical_url, data in matches.items()
        if (
            isinstance(data, dict)
            and data.get("server_id") in server_map
            and server_map[str(data.get("server_id"))].get("type") in _compatible_server_types(str(data.get("provider") or ""))
        )
    }
    if cleaned_matches:
        config["ai_servers_discovery_matches"] = cleaned_matches
    else:
        config.pop("ai_servers_discovery_matches", None)


def match_discovered_candidate(data: dict) -> dict:
    validated, err = validate_json_model(MatchDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    config = facade.load_config_json(None)
    base_url = normalize_base_url((data.get("base_url") or "").strip())
    provider = (data.get("provider") or "").strip()
    server_id = (data.get("server_id") or "").strip()
    if not base_url:
        return {"success": False, "error": "base_url is required"}
    if not server_id:
        return {"success": False, "error": "server_id is required"}

    servers = get_all_servers(config)
    compatible = _compatible_server_types(provider)
    matched = next((s for s in servers if s.id == server_id), None)
    if matched is None:
        return {"success": False, "error": f"Server '{server_id}' not found"}
    if matched.type not in compatible:
        return {"success": False, "error": f"Server '{server_id}' is not compatible with provider '{provider}'"}

    matches = _load_discovery_matches(config)
    matches[base_url] = {
        "server_id": matched.id,
        "provider": provider,
        "matched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    config["ai_servers_discovery_matches"] = matches
    facade.save_config_json(config, "config.json")
    return {"success": True, "server_id": matched.id, "server_name": matched.name}


def unmatch_discovered_candidate(data: dict) -> dict:
    validated, err = validate_json_model(IgnoreDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    config = facade.load_config_json(None)
    base_url = normalize_base_url((data.get("base_url") or "").strip())
    if not base_url:
        return {"success": False, "error": "base_url is required"}
    matches = _load_discovery_matches(config)
    if base_url not in matches:
        return {"success": False, "error": "Match not found"}
    matches.pop(base_url, None)
    if matches:
        config["ai_servers_discovery_matches"] = matches
    else:
        config.pop("ai_servers_discovery_matches", None)
    facade.save_config_json(config, "config.json")
    return {"success": True}


def ignore_discovered_candidate(data: dict) -> dict:
    validated, err = validate_json_model(IgnoreDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    config = facade.load_config_json(None)
    base_url = normalize_base_url((data.get("base_url") or "").strip())
    if not base_url:
        return {"success": False, "error": "base_url is required"}
    ignored = _load_discovery_ignored(config)
    ignored.add(base_url)
    config["ai_servers_discovery_ignored"] = sorted(ignored)
    facade.save_config_json(config, "config.json")
    return {"success": True}


def unignore_discovered_candidate(data: dict) -> dict:
    validated, err = validate_json_model(IgnoreDiscoveredCandidateRequest, data)
    if err:
        return {"success": False, "error": err[0]["error"]}
    assert validated is not None
    data = validated.model_dump(exclude_none=True)

    from core.analysis_api import server_discovery as facade

    config = facade.load_config_json(None)
    base_url = normalize_base_url((data.get("base_url") or "").strip())
    if not base_url:
        return {"success": False, "error": "base_url is required"}
    ignored = _load_discovery_ignored(config)
    if base_url not in ignored:
        return {"success": False, "error": "Ignore entry not found"}
    ignored.discard(base_url)
    if ignored:
        config["ai_servers_discovery_ignored"] = sorted(ignored)
    else:
        config.pop("ai_servers_discovery_ignored", None)
    facade.save_config_json(config, "config.json")
    return {"success": True}
