"""Config and connectivity helpers for LLM endpoint routes."""

from __future__ import annotations

import logging

from core.infra_core.api_errors import api_error, api_result

logger = logging.getLogger(__name__)


def get_config() -> dict:
    from core.services_core.db_state import get_config

    return get_config() or {}


def save_config(config: dict) -> None:
    from core.configuration.api import save_config_json

    save_config_json(config)


def mask_key(key: str) -> str:
    if not key:
        return ""
    from core.settings_core.secret_store import mask_secret

    return mask_secret(key)


def list_endpoints(config: dict) -> dict:
    endpoints = config.get("llm_endpoints", {})
    result = {}
    for category, endpoint in endpoints.items():
        result[category] = {**endpoint, "api_key": mask_key(endpoint.get("api_key", ""))}
    return result


async def update_endpoint(body: dict):
    category = body.get("category", "").strip()
    if not category:
        return api_error("category is required", 400)

    base_url = body.get("base_url", "").strip()
    model = body.get("model", "").strip()
    if not base_url or not model:
        return api_error("base_url and model are required", 400)

    api_key = body.get("api_key", "")
    if api_key and not api_key.startswith("enc:") and "****" not in api_key:
        from core.settings_core.secret_store import encrypt

        api_key = encrypt(api_key)

    timeout = int(body.get("timeout", 60))
    config = get_config()
    config.setdefault("llm_endpoints", {})
    config["llm_endpoints"][category] = {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "timeout": timeout,
    }

    from core.services_core.db_async import run_db_sync

    await run_db_sync(save_config, config)
    return api_result({"category": category})


async def delete_endpoint(category: str):
    config = get_config()
    endpoints = config.get("llm_endpoints", {})
    if category not in endpoints:
        return api_error("not found", 404)
    del endpoints[category]

    from core.services_core.db_async import run_db_sync

    await run_db_sync(save_config, config)
    return api_result({"deleted": category})


async def test_endpoint_connection(body: dict):
    base_url = body.get("base_url", "").strip()
    if not base_url:
        return api_error("base_url is required", 400)

    api_key = body.get("api_key", "")
    if api_key and api_key.startswith("enc:"):
        from core.settings_core.secret_store import decrypt

        api_key = decrypt(api_key)

    import httpx

    headers = {}
    if api_key and "****" not in api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            if resp.status_code < 400:
                return api_result({"models": resp.json()})
            return api_error(f"HTTP {resp.status_code}", 502)
    except Exception as exc:
        logger.warning("LLM endpoint connectivity test failed for %s: %s", base_url, exc)
        return api_error("Endpoint connection failed", 502)
