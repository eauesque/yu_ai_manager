"""Discovery candidate collection for AI servers."""

from __future__ import annotations

import asyncio

from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.llm_endpoint_discovery.local_detect import (
    discover_local_hailo_endpoints,
)
from core.llm_endpoint_discovery.probes import normalize_base_url
from core.settings_core.secret_store import decrypt

from .server_discovery_match import _build_match_state, _load_discovery_ignored
from .server_model_data import get_all_servers

# 同期ネットワークプローブ (Ollama/openai-compat/Hailo) を毎リクエスト走らせると
# 6 秒級になるため、結果を 60 秒キャッシュ。LAN の AI サーバー構成は分単位でしか
# 変わらないので 60 秒は安全側。
_DISCOVERED_CANDIDATES_CACHE = SimpleTTLCache(ttl_seconds=60.0)


def _get_self_web_port(config: dict) -> int:
    raw_port = (config.get("server") or {}).get("port")
    try:
        return int(raw_port) if raw_port else 5000
    except (TypeError, ValueError):
        return 5000


def _discover_local_hailo_candidates(config: dict) -> list:
    hailo_cfg = config.get("hailo") or {}
    raw_hailo_port = hailo_cfg.get("port")
    try:
        hailo_ollama_port = int(raw_hailo_port) if raw_hailo_port else 8000
    except (TypeError, ValueError):
        hailo_ollama_port = 8000
    return list(asyncio.run(discover_local_hailo_endpoints(
        self_web_port=_get_self_web_port(config),
        hailo_ollama_enabled=hailo_cfg.get("enabled", True),
        hailo_ollama_port=hailo_ollama_port,
        existing_backend_urls=frozenset(),
    )))


def _discover_known_openai_compat_candidates(config: dict) -> list[dict]:
    from core.analysis_api import server_discovery as facade

    ai = config.get("ai_analysis") or {}
    base_url = normalize_base_url(ai.get("openai_compat_url", ""))
    if not base_url or not facade._is_private_url(base_url):
        return []
    raw_key = ai.get("openai_compat_api_key", "")
    api_key = decrypt(raw_key) if raw_key else ""
    reachable, reason = facade.probe_openai_compat_models(base_url, api_key=api_key, timeout=3.0)
    return [{
        "provider": "openai_compat",
        "base_url": base_url,
        "display_preferred_url": base_url,
        "scope": "loopback" if "localhost" in base_url or "127.0.0.1" in base_url else "private_lan",
        "source": "local_auto",
        "reachable": reachable,
        "advertisable": False,
        "duplicate_of_canonical_url": None,
        "already_registered": False,
        "suppressed_reason": reason,
        "model": ai.get("openai_compat_model", "") or "",
        "matched_existing_server_id": None,
        "matched_existing_server_name": None,
        "matchable_servers": [],
        "ignored": False,
    }]


def get_discovered_candidates(config: dict | None = None) -> list[dict]:
    # 明示 config 渡しはテストや特殊呼び出し用なのでキャッシュをバイパス。
    # 本番経路 (config=None → load_config_json) のみ TTL キャッシュする。
    if config is not None:
        return _compute_discovered_candidates(config)
    return _DISCOVERED_CANDIDATES_CACHE.get_or_compute(
        "default",
        lambda: _compute_discovered_candidates(None),
    )


def invalidate_discovered_candidates_cache() -> None:
    """Drop cached discovery results (call after server registry mutation)."""
    _DISCOVERED_CANDIDATES_CACHE.invalidate()


def _compute_discovered_candidates(config: dict | None) -> list[dict]:
    from core.analysis_api import server_discovery as facade

    if config is None:
        config = facade.load_config_json(None)

    servers = get_all_servers(config)
    registered_urls = {
        normalize_base_url(s.config.get("base_url", ""))
        for s in servers
        if s.config.get("base_url")
    }
    hailo_registered = any(s.type == "hailo_vlm" for s in servers)
    openai_compat_registered_urls = {
        normalize_base_url(s.config.get("base_url", ""))
        for s in servers
        if s.type == "openai_compat" and s.config.get("base_url")
    }
    ignored_urls = _load_discovery_ignored(config)

    candidates: list[dict] = []
    for endpoint in facade.discover_local_ollama_endpoints():
        canonical = normalize_base_url(endpoint.identity.base_url)
        ignored = canonical in ignored_urls
        matchable_servers, matched_id, matched_name = _build_match_state(
            endpoint.identity.provider,
            canonical,
            servers,
            config,
        )
        candidates.append({
            "provider": endpoint.identity.provider,
            "base_url": canonical,
            "display_preferred_url": endpoint.display_preferred_url or canonical,
            "scope": endpoint.identity.scope,
            "source": endpoint.observation.source,
            "reachable": endpoint.observation.reachable,
            "advertisable": endpoint.observation.advertisable,
            "duplicate_of_canonical_url": endpoint.duplicate_of_canonical_url,
            "already_registered": canonical in registered_urls,
            "ignored": ignored,
            "suppressed_reason": endpoint.suppressed_reason or ("matched_existing" if matched_id else ("policy_hidden" if ignored else None)),
            "matched_existing_server_id": matched_id,
            "matched_existing_server_name": matched_name,
            "matchable_servers": matchable_servers,
        })

    for candidate in _discover_known_openai_compat_candidates(config):
        canonical = normalize_base_url(candidate["base_url"])
        ignored = canonical in ignored_urls
        matchable_servers, matched_id, matched_name = _build_match_state(
            candidate["provider"],
            canonical,
            servers,
            config,
        )
        candidates.append({
            **candidate,
            "base_url": canonical,
            "display_preferred_url": candidate["display_preferred_url"] or canonical,
            "already_registered": canonical in openai_compat_registered_urls,
            "ignored": ignored,
            "suppressed_reason": candidate["suppressed_reason"] or ("matched_existing" if matched_id else ("policy_hidden" if ignored else None)),
            "matched_existing_server_id": matched_id,
            "matched_existing_server_name": matched_name,
            "matchable_servers": matchable_servers,
        })

    for endpoint in facade._discover_local_hailo_candidates(config):
        if endpoint.identity.provider != "hailo_genai":
            continue
        canonical = normalize_base_url(endpoint.identity.base_url)
        ignored = canonical in ignored_urls
        matchable_servers, matched_id, matched_name = _build_match_state(
            endpoint.identity.provider,
            canonical,
            servers,
            config,
        )
        candidates.append({
            "provider": endpoint.identity.provider,
            "base_url": canonical,
            "display_preferred_url": endpoint.display_preferred_url or canonical,
            "scope": endpoint.identity.scope,
            "source": endpoint.observation.source,
            "reachable": endpoint.observation.reachable,
            "advertisable": endpoint.observation.advertisable,
            "duplicate_of_canonical_url": endpoint.duplicate_of_canonical_url,
            "already_registered": hailo_registered,
            "ignored": ignored,
            "suppressed_reason": endpoint.suppressed_reason or ("matched_existing" if matched_id else ("policy_hidden" if ignored else None)),
            "model_name": endpoint.metadata.get("model_name", "qwen2-vl-2b-instruct"),
            "matched_existing_server_id": matched_id,
            "matched_existing_server_name": matched_name,
            "matchable_servers": matchable_servers,
        })
    return candidates
