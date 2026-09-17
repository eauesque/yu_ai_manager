"""Backend discovery: startup poll + periodic refresh + force refresh."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from collections.abc import Callable, Iterable

from .driver import Driver
from .models import BackendInfo, ModelInfo
from .state import BackendCatalog

logger = logging.getLogger("core.llm_router.discovery")


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_default_driver(info: BackendInfo) -> Driver:
    return Driver(base_url=info.base_url, api_key=info.api_key, timeout=3.0)


async def _enrich_ollama_sizes(drv: Driver, models: list[ModelInfo]) -> None:
    """Fetch parameter counts from Ollama /api/show for each model.

    The Driver's base_url typically ends with ``/v1`` for OpenAI compat,
    but ``/api/show`` is a native Ollama endpoint at the root.  We strip
    the trailing ``/v1`` (or ``/v1/``) to build the correct URL.
    """
    import httpx

    ollama_root = drv.base_url
    # Strip /v1 suffix so we hit the native Ollama API root
    if ollama_root.endswith("/v1"):
        ollama_root = ollama_root[:-3]
    elif ollama_root.endswith("/v1/"):
        ollama_root = ollama_root[:-4]

    async def _fetch_one(model: ModelInfo) -> None:
        try:
            async with httpx.AsyncClient(
                base_url=ollama_root, timeout=drv.timeout
            ) as c:
                resp = await c.post(
                    "/api/show",
                    json={"name": model.name},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                param_count = (data.get("model_info") or {}).get(
                    "general.parameter_count"
                )
                if param_count is not None:
                    # param_count is in raw number of parameters;
                    # convert to billions
                    model.size_b = round(int(param_count) / 1e9, 1)
        except Exception:
            logger.warning("step failed", exc_info=True)

    await asyncio.gather(*[_fetch_one(m) for m in models], return_exceptions=True)


async def discover_backend(
    catalog: BackendCatalog,
    info: BackendInfo,
    driver: Driver | None = None,
) -> None:
    """Probe a single backend and update its state in the catalog."""
    drv = driver or _make_default_driver(info)
    try:
        model_ids = await drv.list_models()
    except Exception as exc:
        # Preserve last-known models on info so dispatch can still try cached entries
        info.status = "unreachable"
        info.last_error = str(exc)
        info.last_seen_at = _now_iso()
        catalog.set_backend(info)
        logger.warning("[llm_router] backend %s unreachable: %s", info.alias, exc)
        return

    info.status = "ready"
    info.last_error = None
    info.last_seen_at = _now_iso()
    info.models = [
        ModelInfo(id=f"{info.alias}/{mid}", backend=info.alias, name=mid)
        for mid in model_ids
    ]

    # Ollama: fetch parameter counts via /api/show in parallel
    if getattr(info, "type", None) == "ollama":
        await _enrich_ollama_sizes(drv, info.models)

    catalog.set_backend(info)
    logger.info(
        "[llm_router] backend %s ready (%d models)",
        info.alias,
        len(info.models),
    )


async def discover_all(
    catalog: BackendCatalog,
    backends: Iterable[BackendInfo],
    driver_factory: Callable[[BackendInfo], Driver] | None = None,
) -> None:
    """Probe all backends concurrently. Failures are logged but never raise."""
    factory = driver_factory or _make_default_driver
    tasks = [discover_backend(catalog, b, driver=factory(b)) for b in backends]
    # discover_backend swallows its own exceptions; return_exceptions=True is
    # defensive in case that ever changes
    await asyncio.gather(*tasks, return_exceptions=True)


async def refresh_loop(
    catalog: BackendCatalog,
    backends: list[BackendInfo],
    interval_sec: int,
    driver_factory: Callable[[BackendInfo], Driver] | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Periodically refresh all backends. Cancellation-aware.

    Always re-reads catalog.list_backends() each iteration so that mDNS-
    discovered backends (added after startup) are included. The ``backends``
    parameter is kept for API compatibility but is no longer used directly.
    """
    while True:
        try:
            if stop_event is not None and stop_event.is_set():
                return
            await asyncio.sleep(interval_sec)
            current_backends = catalog.list_backends()
            await discover_all(catalog, current_backends, driver_factory=driver_factory)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("[llm_router] refresh loop iteration failed: %s", exc)
