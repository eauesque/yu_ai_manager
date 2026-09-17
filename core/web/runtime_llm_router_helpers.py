"""Helper functions for runtime_llm_router."""

import logging

logger = logging.getLogger(__name__)


def start_llm_router_refresh_loop() -> None:
    import asyncio
    import os

    if os.environ.get("TAGDB_DISABLE_LLM_ROUTER_REFRESH", "").lower() in ("1", "true", "yes"):
        logger.info("  [LLM_ROUTER] Periodic refresh disabled via env")
        return

    from core.llm_router.discovery import refresh_loop
    from core.llm_router.state import get_catalog

    cat = get_catalog()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(refresh_loop(cat, [], interval_sec=300))
    except RuntimeError:
        pass


def _detect_local_ollama(timeout: float = 1.0) -> "tuple[str, str] | None":
    from core.llm_endpoint_discovery.local_detect import discover_local_ollama_endpoints

    for endpoint in discover_local_ollama_endpoints(timeout=timeout):
        if endpoint.observation.advertisable:
            return (endpoint.identity.base_url, endpoint.identity.provider)
    return None
