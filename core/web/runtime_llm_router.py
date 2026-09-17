"""LLM Router startup initialization for the web_ui runtime."""

import logging

from core.web.runtime_llm_router_helpers import (
    _detect_local_ollama,
    start_llm_router_refresh_loop,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_detect_local_ollama",
    "init_llm_router_discovery",
    "start_llm_router_refresh_loop",
]


async def init_llm_router_discovery(config: dict) -> None:
    """Populate the LLM router catalog from config and run startup discovery.

    Async because Phase A (Hailo LLM auto-detection) runs an httpx probe
    against localhost:8000 to check for a running hailo-ollama. See
    core/llm_router/hailo_detect.py.
    """
    import os

    router_cfg = config.get("llm_router", {}) or {}
    if not router_cfg.get("enabled", True):
        logger.info("  [LLM_ROUTER] Disabled in config")
        return

    if os.environ.get("TAGDB_DISABLE_LLM_ROUTER", "").lower() in ("1", "true", "yes"):
        logger.info("  [LLM_ROUTER] Disabled via TAGDB_DISABLE_LLM_ROUTER")
        return

    from core.analysis_api.config_ops import _is_private_url
    from core.llm_endpoint_discovery.local_detect import (
        discover_local_hailo_endpoints,
        discover_local_ollama_endpoints,
    )
    from core.llm_endpoint_discovery.probes import (
        normalize_base_url,
        probe_openai_compat_models,
    )
    from core.llm_router.discovery import discover_all
    from core.llm_router.models import BackendInfo
    from core.llm_router.state import get_catalog
    from routes import llm_router as llm_router_module

    cat = get_catalog()
    cat.clear()

    # Apply auth config
    auth_cfg = router_cfg.get("auth", {}) or {}
    api_key_raw = auth_cfg.get("api_key", "")
    if api_key_raw.startswith("enc:"):
        try:
            from core.settings_core.secret_store import decrypt
            api_key_raw = decrypt(api_key_raw)
        except Exception:
            logger.warning("  [LLM_ROUTER] Failed to decrypt api_key")
            api_key_raw = ""
    # Whitelist accepted auth modes — env var override is convenient for ops
    # but must not silently accept arbitrary strings (e.g. typos that fall
    # through to the unknown-mode 401 path, or future modes spelled wrong).
    _ALLOWED_AUTH_MODES = ("none", "loopback", "api_key")
    auth_mode_env = os.environ.get("TAGDB_LLM_ROUTER_AUTH_MODE")
    if auth_mode_env and auth_mode_env not in _ALLOWED_AUTH_MODES:
        logger.warning(
            "  [LLM_ROUTER] Ignoring invalid TAGDB_LLM_ROUTER_AUTH_MODE=%r (allowed: %s)",
            auth_mode_env,
            ", ".join(_ALLOWED_AUTH_MODES),
        )
        auth_mode_env = None
    auth_mode = auth_mode_env or auth_cfg.get("mode", "loopback")
    if auth_mode not in _ALLOWED_AUTH_MODES:
        logger.warning(
            "  [LLM_ROUTER] Invalid auth.mode=%r in config, falling back to 'loopback'",
            auth_mode,
        )
        auth_mode = "loopback"
    llm_router_module.configure_auth(
        {
            "mode": auth_mode,
            "api_key": api_key_raw,
            "allow_loopback_bypass": auth_cfg.get("allow_loopback_bypass", True),
        }
    )

    # Build BackendInfo entries
    backends: list[BackendInfo] = []
    for entry in router_cfg.get("backends") or []:
        b = BackendInfo(
            alias=entry["alias"],
            base_url=entry["base_url"],
            type=entry.get("type", "ollama"),
            auto_discover=entry.get("auto_discover", True),
            respect_vision_load=entry.get("slo", {}).get("respect_vision_load", False),
            source="static",
        )
        backends.append(b)
        cat.set_backend(b)

    cat.set_aliases(router_cfg.get("aliases") or {})

    for physical_id, meta in (router_cfg.get("model_metadata") or {}).items():
        cat.set_metadata(physical_id, meta)

    hailo_cfg = router_cfg.get("hailo_ollama", {}) or {}
    existing_urls = frozenset(
        normalize_base_url(entry.get("base_url", ""))
        for entry in (router_cfg.get("backends") or [])
        if entry.get("base_url")
    )

    # Defensive: config["server"]["port"] may be absent, null, or a string.
    raw_port = (config.get("server") or {}).get("port")
    try:
        self_web_port = int(raw_port) if raw_port else 5000
    except (TypeError, ValueError):
        self_web_port = 5000

    raw_hailo_port = hailo_cfg.get("port")
    try:
        hailo_ollama_port = int(raw_hailo_port) if raw_hailo_port else 8000
    except (TypeError, ValueError):
        hailo_ollama_port = 8000
    if not (1 <= hailo_ollama_port <= 65535):
        logger.warning(
            "  [LLM_ROUTER] hailo_ollama.port=%d out of range, using default 8000",
            hailo_ollama_port,
        )
        hailo_ollama_port = 8000

    hailo_endpoints = await discover_local_hailo_endpoints(
        self_web_port=self_web_port,
        hailo_ollama_enabled=hailo_cfg.get("enabled", True),
        hailo_ollama_port=hailo_ollama_port,
        existing_backend_urls=existing_urls,
    )

    for endpoint in hailo_endpoints:
        if endpoint.identity.provider == "hailo_genai":
            device_count = int(endpoint.metadata.get("device_count", "1") or "1")
            if cat.get_backend("hailo-local") is None:
                if device_count <= 1:
                    cat.set_backend(BackendInfo(
                        alias="hailo-local",
                        base_url=endpoint.identity.base_url,
                        type="hailo-ollama",
                        auto_discover=True,
                        source="static",
                    ))
                    logger.info(
                        "  [LLM_ROUTER] Auto-registered Hailo extension backend: hailo-local"
                    )
                else:
                    for idx in range(device_count):
                        alias = f"hailo-local-{idx}"
                        if cat.get_backend(alias) is not None:
                            continue
                        cat.set_backend(BackendInfo(
                            alias=alias,
                            base_url=endpoint.identity.base_url,
                            type="hailo-ollama",
                            auto_discover=True,
                            source="static",
                        ))
                        logger.info(
                            "  [LLM_ROUTER] Auto-registered Hailo extension backend: %s (device %d of %d)",
                            alias, idx, device_count,
                        )
                    if cat.get_backend("hailo-local") is None:
                        cat.set_backend(BackendInfo(
                            alias="hailo-local",
                            base_url=endpoint.identity.base_url,
                            type="hailo-ollama",
                            auto_discover=True,
                            source="static",
                        ))
        elif endpoint.identity.provider == "hailo_ollama":
            if cat.get_backend("hailo-ollama-local") is None:
                cat.set_backend(BackendInfo(
                    alias="hailo-ollama-local",
                    base_url=endpoint.identity.base_url,
                    type="hailo-ollama",
                    auto_discover=True,
                    source="static",
                ))
                logger.info(
                    "  [LLM_ROUTER] Auto-registered hailo-ollama backend: hailo-ollama-local"
                )

    local_ollama = next(iter(discover_local_ollama_endpoints()), None)
    if local_ollama is not None and cat.get_backend("ollama-local") is None:
        router_base_url = normalize_base_url(f"{local_ollama.identity.base_url}/v1")
        if router_base_url not in existing_urls:
            cat.set_backend(BackendInfo(
                alias="ollama-local",
                base_url=router_base_url,
                type="ollama",
                auto_discover=True,
                source="static",
            ))
            logger.info(
                "  [LLM_ROUTER] Auto-registered local Ollama backend: ollama-local"
            )

    ai_cfg = config.get("ai_analysis", {}) or {}
    openai_compat_url = normalize_base_url(ai_cfg.get("openai_compat_url", ""))
    openai_compat_api_key = ai_cfg.get("openai_compat_api_key", "")
    if isinstance(openai_compat_api_key, str) and openai_compat_api_key.startswith("enc:"):
        try:
            from core.settings_core.secret_store import decrypt
            openai_compat_api_key = decrypt(openai_compat_api_key)
        except Exception:
            logger.warning("  [LLM_ROUTER] Failed to decrypt ai_analysis.openai_compat_api_key")
            openai_compat_api_key = ""
    if (
        openai_compat_url
        and _is_private_url(openai_compat_url)
        and cat.get_backend("openai-compat-local") is None
    ):
        reachable, reason = probe_openai_compat_models(
            openai_compat_url,
            api_key=openai_compat_api_key or "",
            timeout=3.0,
            user_agent="yu_ai_manager/llm_router",
        )
        router_base_url = normalize_base_url(f"{openai_compat_url}/v1")
        if reachable and router_base_url not in existing_urls:
            cat.set_backend(BackendInfo(
                alias="openai-compat-local",
                base_url=router_base_url,
                api_key=openai_compat_api_key or "",
                type="openai-compat",
                auto_discover=True,
                source="static",
            ))
            logger.info(
                "  [LLM_ROUTER] Auto-registered local OpenAI Compatible backend: openai-compat-local"
            )
        elif reason == "auth_required":
            logger.info(
                "  [LLM_ROUTER] Skipped local OpenAI Compatible auto-register: auth required"
            )

    # Restore disabled state BEFORE the probe loop is scheduled.
    # This is intentionally synchronous: any await before set_disabled
    # completes would let the freshly-scheduled discover_all task race
    # ahead and re-enable the backend via its first successful probe.
    # See spec §5.5 for the full ordering rationale.
    from core.llm_router import persistence
    persisted = persistence.load_state()
    for alias in persisted.get("disabled_aliases", []):
        if not cat.set_disabled(alias, True):
            logger.info(
                "  [LLM_ROUTER] persisted disabled alias %r has no matching "
                "backend (deferred until discovery)", alias,
            )

    # Run startup discovery synchronously so the catalog is populated
    # before list_models() is called (fixes auto:* resolved_to = null
    # on first request).
    if backends:
        await discover_all(cat, backends)

    logger.info(
        "  [LLM_ROUTER] Initialized: %d backends, %d aliases, auth=%s",
        len(backends),
        len(router_cfg.get("aliases") or {}),
        auth_mode,
    )
