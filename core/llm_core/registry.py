"""Category → LLMClient mapping from config.json."""

from __future__ import annotations

import logging

from .client import LLMClient

logger = logging.getLogger("core.llm_core")


def _get_config() -> dict:
    """Get current config from app state (runtime fallback)."""
    try:
        from core.services_core.db_state import get_config
        return get_config() or {}
    except Exception:
        return {}


def decrypt(value: str) -> str:
    """Decrypt enc: prefixed values."""
    try:
        from core.settings_core.secret_store import decrypt as _decrypt
        from core.settings_core.secret_store import is_encrypted
        if is_encrypted(value):
            return _decrypt(value)
    except ImportError:
        pass
    return value


def get_llm_client(
    category: str,
    *,
    config: dict | None = None,
) -> LLMClient | None:
    """Get an LLMClient for the given category, or None if not configured."""
    cfg = config if config is not None else _get_config()
    endpoints = cfg.get("llm_endpoints", {})
    ep = endpoints.get(category)
    if not ep or not isinstance(ep, dict):
        return None

    base_url = ep.get("base_url", "").strip()
    model = ep.get("model", "").strip()
    if not base_url or not model:
        logger.warning("LLM endpoint [%s] missing base_url or model", category)
        return None

    api_key = ep.get("api_key", "")
    if api_key:
        api_key = decrypt(api_key)

    timeout = float(ep.get("timeout", 60))

    return LLMClient(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        category=category,
    )
