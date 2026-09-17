"""Engine availability checks and resolution with fallback logic."""

from core.analysis_api.config_ops import resolve_engine_kwargs as _resolve
from core.analysis_api.server_model_resolve import (
    _is_hailo_vlm_available,
    _is_ollama_available,
    _is_openai_compat_available,
)
from core.configuration.api import load_config_json
from core.settings_core.secret_store import decrypt


def _is_engine_local(engine_type: str, engine_kwargs: dict) -> bool:
    """Determine whether the engine runs locally (loopback / private IP)."""
    from core.analysis_api.config_ops import _is_private_url

    if engine_type in ("claude_api", "openai"):
        return False
    if engine_type == "hailo_vlm":
        return True
    if engine_type == "ollama":
        return _is_private_url(engine_kwargs.get("base_url", "http://localhost:11434"))
    if engine_type == "openai_compat":
        return _is_private_url(engine_kwargs.get("base_url", ""))
    return False


def _resolve_with_fallback(ai_config: dict, server_id: str | None = None):
    """Resolve engine, falling back to local engines when needed.

    When ``ai_servers`` is configured, delegates to server_registry.
    Otherwise falls back to legacy resolution logic.

    When ``fallback_local_only`` is enabled, only engines at loopback /
    private-network addresses are considered.  Cloud APIs (Claude, OpenAI)
    and non-local OpenAI-compat servers are skipped entirely.
    """
    # ai_servers mode: delegate to registry
    from core.analysis_api.server_registry import has_servers, resolve_active_server
    config = load_config_json(None)
    if has_servers(config):
        return resolve_active_server(config, server_id=server_id)

    # Legacy mode: existing logic
    from core.analysis_api.config_ops import _is_private_url

    local_only = bool(ai_config.get("fallback_local_only", False))
    language = ai_config.get("language", "ja")
    engine_type, engine_kwargs = _resolve(ai_config)

    # Local-only mode: skip if selected engine is remote
    if local_only and not _is_engine_local(engine_type, engine_kwargs):
        engine_type = None  # Fall through to fallback

    needs_fallback = engine_type is None or (
        (engine_type == "claude_api" and not engine_kwargs.get("api_key"))
        or (engine_type == "openai" and not engine_kwargs.get("api_key"))
    )
    if not needs_fallback:
        return engine_type, engine_kwargs, None

    # Fallback 1: OpenAI-compatible server (private URLs only in local-only mode)
    compat_url = ai_config.get("openai_compat_url", "")
    compat_key = decrypt(ai_config.get("openai_compat_api_key", ""))
    if compat_url and (not local_only or _is_private_url(compat_url)):  # noqa: SIM102
        if _is_openai_compat_available(compat_url, compat_key):
            return "openai_compat", {
                "base_url": compat_url,
                "api_key": compat_key,
                "model": ai_config.get("openai_compat_model", ""),
                "language": language,
            }, None

    # Fallback 2: Ollama (private URLs only in local-only mode)
    ollama_url = ai_config.get("ollama_url", "http://localhost:11434")
    if (not local_only or _is_private_url(ollama_url)) and _is_ollama_available(ollama_url):
        return "ollama", {
            "base_url": ollama_url,
            "model": ai_config.get("ollama_model", "llava:latest"),
            "language": language,
        }, None

    # Fallback 3: Hailo VLM (always local)
    hailo_model = ai_config.get("hailo_vlm_model", "qwen2-vl-2b-instruct")
    if _is_hailo_vlm_available(hailo_model):
        return "hailo_vlm", {"model_name": hailo_model, "language": language}, None

    if local_only:
        return None, None, (
            "ローカル限定モードが有効です。"
            "ローカルエンジン (Ollama / OpenAI互換 / Hailo VLM) に接続できません。"
            "ローカルサーバーを起動するか、設定を確認してください。"
        )
    return None, None, (
        "APIkeyが未設定で、OpenAI互換サーバー・Ollama・Hailo VLMにも接続できません。"
        "Toolsページで API keyを設定するか、ローカルサーバーを利用可能にしてください。"
    )


def _resolve_override(ai_config: dict, engine_type: str, model_override: str | None = None):
    """Resolve engine with explicit engine type (and optional model) override."""
    language = ai_config.get("language", "ja")

    if engine_type == "claude_api":
        api_key = decrypt(ai_config.get("api_key", ""))
        if not api_key:
            return None, None, "Claude API key is not configured"
        return engine_type, {
            "api_key": api_key,
            "model": model_override or ai_config.get("model", "claude-sonnet-4-6"),
            "language": language,
        }, None

    if engine_type == "openai":
        api_key = decrypt(ai_config.get("openai_api_key", ""))
        if not api_key:
            return None, None, "OpenAI API key is not configured"
        return engine_type, {
            "api_key": api_key,
            "model": model_override or ai_config.get("openai_model", "gpt-4o-mini"),
            "language": language,
        }, None

    if engine_type == "openai_compat":
        url = ai_config.get("openai_compat_url", "")
        if not url:
            return None, None, "OpenAI Compatible URL is not configured"
        key = decrypt(ai_config.get("openai_compat_api_key", ""))
        if not _is_openai_compat_available(url, key):
            return None, None, "OpenAI Compatible server is not reachable"
        return engine_type, {
            "base_url": url,
            "api_key": key,
            "model": model_override or ai_config.get("openai_compat_model", ""),
            "language": language,
        }, None

    if engine_type == "ollama":
        url = ai_config.get("ollama_url", "http://localhost:11434")
        if not _is_ollama_available(url):
            return None, None, "Ollama is not reachable"
        return engine_type, {
            "base_url": url,
            "model": model_override or ai_config.get("ollama_model", "llava:latest"),
            "language": language,
        }, None

    if engine_type == "hailo_vlm":
        model = ai_config.get("hailo_vlm_model", "qwen2-vl-2b-instruct")
        if not _is_hailo_vlm_available(model):
            return None, None, "Hailo VLM is not available"
        return engine_type, {"model_name": model, "language": language}, None

    return None, None, f"Unknown engine type: {engine_type}"
