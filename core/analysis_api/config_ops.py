"""Analysis API configuration operations."""

import ipaddress
from urllib.parse import urlparse

from core.configuration.api import load_config_json, save_config_json
from core.infra_core.simple_ttl_cache import SimpleTTLCache
from core.settings_core.secret_store import decrypt, encrypt, mask_secret

_engines_cache = SimpleTTLCache(ttl_seconds=30.0)

_CONFIG_KEYS = [
    "engine", "api_key", "model",
    "ollama_url", "ollama_model",
    "openai_api_key", "openai_model",
    "openai_compat_url", "openai_compat_api_key", "openai_compat_model",
    "hailo_vlm_model",
    "fallback_local_only",
    "language",
]


def get_analysis_config():
    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})
    masked = dict(ai_config)
    for k in ("api_key", "openai_api_key", "openai_compat_api_key"):
        raw = masked.get(k, "")
        if raw:
            masked[k] = mask_secret(decrypt(raw))
    masked["is_local"] = is_local_engine(ai_config)

    # Add server registry info
    from core.analysis_api.server_registry import (
        get_active_server_id,
        get_servers_with_status,
        has_servers,
    )
    masked["has_servers"] = has_servers(config)
    if masked["has_servers"]:
        masked["servers"] = get_servers_with_status(config)
        masked["active_server"] = get_active_server_id(config)

    return masked


def save_analysis_config(data: dict):
    config = load_config_json(None)
    if "ai_analysis" not in config:
        config["ai_analysis"] = {}
    _SECRET_KEYS = {"api_key", "openai_api_key", "openai_compat_api_key"}
    for key in _CONFIG_KEYS:
        if key in data:
            value = data[key]
            # Don't overwrite masked values
            if isinstance(value, str) and "..." in value:
                continue
            # Encrypt secret keys
            if key in _SECRET_KEYS and isinstance(value, str) and value:
                value = encrypt(value)
            config["ai_analysis"][key] = value
    save_config_json(config, "config.json")
    _engines_cache.invalidate()
    return {"success": True}, 200


def resolve_engine_kwargs(ai_config: dict) -> tuple[str, dict]:
    """Resolve engine type and kwargs from ai_analysis config dict."""
    engine_type = ai_config.get("engine", "claude_api")
    language = ai_config.get("language", "ja")
    if engine_type == "ollama":
        return engine_type, {
            "base_url": ai_config.get("ollama_url", "http://localhost:11434"),
            "model": ai_config.get("ollama_model", "llava:latest"),
            "language": language,
        }
    if engine_type == "openai":
        return engine_type, {
            "api_key": decrypt(ai_config.get("openai_api_key", "")),
            "model": ai_config.get("openai_model", "gpt-4o-mini"),
            "language": language,
        }
    if engine_type == "openai_compat":
        return engine_type, {
            "base_url": ai_config.get("openai_compat_url", ""),
            "api_key": decrypt(ai_config.get("openai_compat_api_key", "")),
            "model": ai_config.get("openai_compat_model", ""),
            "language": language,
        }
    if engine_type == "hailo_vlm":
        return engine_type, {
            "model_name": ai_config.get("hailo_vlm_model", "qwen2-vl-2b-instruct"),
            "language": language,
        }
    # claude_api / local / other
    return engine_type, {
        "api_key": decrypt(ai_config.get("api_key", "")),
        "model": ai_config.get("model", "claude-sonnet-4-6"),
        "language": language,
    }


def _is_private_url(url: str) -> bool:
    """Determine whether the URL host is a loopback or private IP.

    For DNS names, resolve first and then check the IP address.
    Unresolvable hosts are treated as non-private (safe side).
    """
    import socket

    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host in ("localhost", ""):
            return True
        try:
            addr = ipaddress.ip_address(host)
            return addr.is_loopback or addr.is_private
        except ValueError:
            # DNS name: resolve and re-check by IP
            try:
                resolved = socket.gethostbyname(host)
                addr = ipaddress.ip_address(resolved)
                return addr.is_loopback or addr.is_private
            except (socket.gaierror, ValueError):
                return False
    except (ValueError, TypeError):
        return False


def get_available_engines() -> list:
    """Return a list of configured and reachable engines (30s TTL cache).

    When fallback_local_only is enabled, cloud engines are excluded.
    Ollama / OpenAI Compatible entries include their model lists.

    Each entry: {"type", "label", "model", "models"(optional)}
    """
    cached = _engines_cache.peek("engines")
    if cached is not None:
        return cached
    result = _compute_available_engines()
    _engines_cache.put("engines", result)
    return result


def _compute_available_engines() -> list:
    import logging

    from core.analysis_api.single_ops import (
        _is_hailo_vlm_available,
        _is_ollama_available,
        _is_openai_compat_available,
    )

    logger = logging.getLogger(__name__)
    config = load_config_json(None)
    ai = config.get("ai_analysis", {})
    local_only = bool(ai.get("fallback_local_only", False))
    engines = []

    # Claude API (cloud -- excluded in local_only mode)
    if not local_only and ai.get("api_key"):
        model = ai.get("model", "claude-sonnet-4-6")
        engines.append({
            "type": "claude_api",
            "label": "Claude API",
            "model": model,
            "models": [
                "claude-sonnet-4-6",
                "claude-opus-4-6",
                "claude-haiku-4-5",
            ],
        })

    # OpenAI (cloud -- excluded in local_only mode)
    if not local_only and ai.get("openai_api_key"):
        model = ai.get("openai_model", "gpt-4o-mini")
        engines.append({
            "type": "openai",
            "label": "OpenAI",
            "model": model,
            "models": [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
            ],
        })

    # OpenAI Compatible (private URLs only in local_only mode)
    compat_url = ai.get("openai_compat_url", "")
    if compat_url and (not local_only or _is_private_url(compat_url)):
        compat_key = decrypt(ai.get("openai_compat_api_key", ""))
        if _is_openai_compat_available(compat_url, compat_key):
            model = ai.get("openai_compat_model", "")
            models = _fetch_openai_compat_models(compat_url, compat_key, logger)
            engines.append({
                "type": "openai_compat",
                "label": "OpenAI Compatible",
                "model": model,
                "models": models,
            })

    # Ollama (private URLs only in local_only mode)
    ollama_url = ai.get("ollama_url", "http://localhost:11434")
    if (not local_only or _is_private_url(ollama_url)) and _is_ollama_available(ollama_url):
        model = ai.get("ollama_model", "llava:latest")
        models = _fetch_ollama_models(ollama_url, logger)
        engines.append({
            "type": "ollama",
            "label": "Ollama",
            "model": model,
            "models": models,
        })

    # Hailo VLM (always local)
    hailo_model = ai.get("hailo_vlm_model", "qwen2-vl-2b-instruct")
    if _is_hailo_vlm_available(hailo_model):
        engines.append({
            "type": "hailo_vlm",
            "label": "Hailo VLM",
            "model": hailo_model,
            "models": [hailo_model],
        })

    return engines


def _fetch_ollama_models(url: str, logger) -> list:
    """Retrieve model name list from Ollama. Returns empty list on failure."""
    try:
        from core.analysis.ollama_utils import list_ollama_models
        return [m["name"] for m in list_ollama_models(url)]
    except Exception as e:
        logger.debug("Failed to fetch Ollama models: %s", e)
        return []


def _fetch_openai_compat_models(url: str, api_key: str, logger) -> list:
    """Retrieve model ID list from OpenAI Compatible server. Returns empty list on failure."""
    try:
        from core.analysis.openai_compat_utils import list_openai_compat_models
        return [m["id"] for m in list_openai_compat_models(url, api_key, allow_local=True)]
    except Exception as e:
        logger.debug("Failed to fetch OpenAI-compat models: %s", e)
        return []


def is_local_engine(ai_config: dict) -> bool:
    """Determine whether the engine is local (no cost)."""
    engine = ai_config.get("engine", "claude_api")
    if engine == "hailo_vlm":
        return True
    if engine == "ollama":
        url = ai_config.get("ollama_url", "http://localhost:11434")
        return _is_private_url(url)
    if engine == "openai_compat":
        url = ai_config.get("openai_compat_url", "")
        return _is_private_url(url)
    return False
