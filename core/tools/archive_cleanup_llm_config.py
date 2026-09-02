"""Archive cleanup LLM configuration -- dedicated LLM settings for archive verification.

Manages dedicated settings (separate from AI Analysis) in the "archive_cleanup_llm" section of config.json.
Hailo VLM is excluded as it is unsuitable for text-only tasks.
"""

from __future__ import annotations

from typing import Any

from core.configuration.api import load_config_json, save_config_json

_SECTION = "archive_cleanup_llm"

_CONFIG_KEYS = [
    "engine", "api_key", "model",
    "ollama_url", "ollama_model",
    "openai_api_key", "openai_model",
    "openai_compat_url", "openai_compat_api_key", "openai_compat_model",
]

_DEFAULTS: dict[str, str] = {
    "engine": "ollama",
    "api_key": "",
    "model": "claude-sonnet-4-6",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3:8b",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "openai_compat_url": "",
    "openai_compat_api_key": "",
    "openai_compat_model": "",
}


def _mask_key(value: str) -> str:
    if not value or len(value) < 8:
        return value
    return value[:4] + "..." + value[-2:]


def get_ac_llm_config() -> dict[str, Any]:
    """Get configuration (with API keys masked)."""
    config = load_config_json(None)
    section = config.get(_SECTION, {})
    result: dict[str, Any] = {}
    for key in _CONFIG_KEYS:
        result[key] = section.get(key, _DEFAULTS.get(key, ""))
    # Mask secrets
    from core.settings_core.secret_store import decrypt, mask_secret
    for key in ("api_key", "openai_api_key", "openai_compat_api_key"):
        raw = result.get(key, "")
        if raw:
            result[key] = mask_secret(decrypt(raw))
    return result


def save_ac_llm_config(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Save configuration. Masked keys are not overwritten."""
    from core.settings_core.secret_store import encrypt
    config = load_config_json(None)
    if _SECTION not in config:
        config[_SECTION] = {}
    _SECRET_KEYS = {"api_key", "openai_api_key", "openai_compat_api_key"}
    for key in _CONFIG_KEYS:
        if key not in data:
            continue
        value = data[key]
        # Masked values ("sk-..." etc.) keep the original value
        if isinstance(value, str) and "..." in value:
            continue
        # Encrypt secret keys
        if key in _SECRET_KEYS and isinstance(value, str) and value:
            value = encrypt(value)
        config[_SECTION][key] = value
    save_config_json(config, "config.json")
    return {"success": True}, 200


def resolve_ac_llm_engine(
    llm_config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], str | None]:
    """Resolve engine (Hailo VLM excluded, text-only).

    Returns (engine_type, kwargs, error_or_none).
    """
    from core.settings_core.secret_store import decrypt
    if llm_config is None:
        config = load_config_json(None)
        llm_config = config.get(_SECTION, {})

    engine = llm_config.get("engine", _DEFAULTS["engine"])

    # Hailo VLM is unsuitable for text-only tasks
    if engine == "hailo_vlm":
        return "", {}, "Hailo VLM is not supported for text-only verification"

    if engine == "ollama":
        return engine, {
            "base_url": llm_config.get("ollama_url", _DEFAULTS["ollama_url"]),
            "model": llm_config.get("ollama_model", _DEFAULTS["ollama_model"]),
        }, None

    if engine == "openai":
        api_key = decrypt(llm_config.get("openai_api_key", ""))
        if not api_key:
            return "", {}, "OpenAI API key is required"
        return engine, {
            "api_key": api_key,
            "model": llm_config.get("openai_model", _DEFAULTS["openai_model"]),
        }, None

    if engine == "openai_compat":
        return engine, {
            "base_url": llm_config.get("openai_compat_url", ""),
            "api_key": decrypt(llm_config.get("openai_compat_api_key", "")),
            "model": llm_config.get("openai_compat_model", ""),
        }, None

    if engine == "claude_api":
        api_key = decrypt(llm_config.get("api_key", ""))
        if not api_key:
            return "", {}, "Claude API key is required"
        return engine, {
            "api_key": api_key,
            "model": llm_config.get("model", _DEFAULTS["model"]),
        }, None

    return "", {}, f"Unknown engine: {engine}"
