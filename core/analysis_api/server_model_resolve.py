"""AI server resolution and availability checking.

Resolves the active AI server with priority-based fallback,
and provides availability checks for each server type.
"""

from __future__ import annotations

import logging
import urllib.request

from core.configuration.api import load_config_json

from .server_model_data import (
    ServerEntry,
    get_active_server_id,
    get_all_servers,
    get_language,
    is_fallback_local_only,
)

logger = logging.getLogger(__name__)


# ── Server resolution (with fallback) ─────────────────────────────

def resolve_active_server(
    config: dict | None = None,
    server_id: str | None = None,
) -> tuple[str | None, dict | None, str | None]:
    """Resolve the active server with priority-based fallback.

    Args:
        config: config dict (auto-loaded when None)
        server_id: prefer this server when specified

    Returns:
        (engine_type, engine_kwargs, error_message)
        error_message is None on success.
    """
    if config is None:
        config = load_config_json(None)

    servers = get_all_servers(config)
    if not servers:
        return None, None, "AI サーバーが登録されていません。"

    language = get_language(config)
    local_only = is_fallback_local_only(config)

    # Try the specified or active server first
    target_id = server_id or get_active_server_id(config)

    if target_id:
        for s in servers:
            if s.id == target_id and s.enabled:
                if local_only and not _is_server_local(s):
                    break  # Local-only mode with non-local server -- fallback
                kwargs = _build_kwargs(s, language)
                if _check_available(s):
                    return s.type, kwargs, None
                break  # Found but not reachable -- fallback

    # Fallback: scan by priority order
    for s in servers:
        if not s.enabled:
            continue
        if local_only and not _is_server_local(s):
            continue
        kwargs = _build_kwargs(s, language)
        if _check_available(s):
            logger.info("AI サーバーフォールバック: %s (%s)", s.name, s.type)
            return s.type, kwargs, None

    if local_only:
        return None, None, (
            "ローカル限定モードが有効です。"
            "利用可能なローカル AI サーバーがありません。"
        )
    return None, None, "利用可能な AI サーバーがありません。サーバー設定を確認してください。"


# ── Internal helpers ──────────────────────────────────────────────

def _build_kwargs(entry: ServerEntry, language: str) -> dict:
    """Build engine kwargs from a ServerEntry."""
    kwargs = dict(entry.config)
    kwargs.setdefault("language", language)
    return kwargs


def _is_server_local(entry: ServerEntry) -> bool:
    """Determine whether a server is local (loopback / private IP)."""
    from core.analysis_api.config_ops import _is_private_url

    if entry.type in ("claude_api", "openai"):
        return False
    if entry.type == "hailo_vlm":
        return True
    url = entry.config.get("base_url", "")
    return _is_private_url(url) if url else False


def _check_available(entry: ServerEntry) -> bool:
    """Check whether a server is reachable."""
    t = entry.type
    cfg = entry.config

    if t == "claude_api":
        return bool(cfg.get("api_key"))
    if t == "openai":
        return bool(cfg.get("api_key"))
    if t == "ollama":
        url = cfg.get("base_url", "http://localhost:11434")
        return _is_ollama_available(url)
    if t == "openai_compat":
        url = cfg.get("base_url", "")
        api_key = cfg.get("api_key", "")
        return _is_openai_compat_available(url, api_key)
    if t == "hailo_vlm":
        return _is_hailo_vlm_available(cfg.get("model_name", "qwen2-vl-2b-instruct"))
    return False


def _is_ollama_available(url: str = "http://localhost:11434") -> bool:
    from core.llm_endpoint_discovery.probes import probe_ollama_tags

    return probe_ollama_tags(url, timeout=3.0)


def _is_openai_compat_available(url: str, api_key: str = "") -> bool:
    if not url:
        return False
    try:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(f"{url.rstrip('/')}/v1/models", headers=headers)
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _is_hailo_vlm_available(model_name: str = "qwen2-vl-2b-instruct") -> bool:
    try:
        import importlib.util
        from pathlib import Path

        from core.hailo_device_core.device_manager import is_genai_available
        # Load from the Hailo GenAI extension module by file path.
        _spec = importlib.util.spec_from_file_location(
            "hailo_genai_model_download",
            Path(__file__).resolve().parents[2] / "extensions" / "builtin_hailo_genai" / "core_impl" / "model_download.py")
        _dl_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_dl_mod)
        is_hef_available = _dl_mod.is_hef_available
        return is_genai_available() and is_hef_available(model_name)
    except (ImportError, FileNotFoundError, AttributeError):
        return False
