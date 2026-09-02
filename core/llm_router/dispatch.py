"""Target resolution and dispatch entrypoint for the LLM router."""

from __future__ import annotations

import re
from collections.abc import Callable

from .driver import Driver
from .errors import BackendDisabledError, BackendNotFoundError
from .models import BackendInfo, ModelInfo
from .state import BackendCatalog, get_catalog


def _estimate_params_b(model_name: str) -> float:
    """Estimate parameter count (billions) from model name. Returns 0.0 if unknown.

    For MoE models with an active-parameter tag (e.g. "A4B"), use the active
    count instead of the total so that auto:small/medium/large classification
    reflects real per-request cost.
    """
    # MoE active-parameter pattern: e.g. "27B-A4B", "gemma4...A4B"
    active = re.search(r"A(\d+(?:\.\d+)?)\s*[Bb]", model_name)
    if active:
        return float(active.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Bb]", model_name)
    if m:
        return float(m.group(1))
    return 0.0


def _resolve_auto(
    catalog: BackendCatalog, target: str
) -> tuple[BackendInfo, str, str]:
    """Resolve auto:* targets by picking from ready, non-disabled models."""
    category = target.split(":", 1)[1]

    candidates: list[tuple[BackendInfo, ModelInfo, float]] = []
    for backend in catalog.list_backends():
        if backend.status != "ready" or backend.disabled:
            continue
        for model in backend.models:
            size = model.size_b or _estimate_params_b(model.name)
            candidates.append((backend, model, size))

    if not candidates:
        raise BackendNotFoundError(
            f"no ready backends available for {target}"
        )

    # Exclude vision-only models from non-vision categories
    if category != "vision":
        candidates = [
            c for c in candidates
            if not re.search(r"vl|vision|llava", c[1].name, re.IGNORECASE)
        ]
        if not candidates:
            raise BackendNotFoundError(
                f"no non-vision models available for {target}"
            )

    if category == "vision":
        vision = [
            c for c in candidates
            if re.search(r"vl|vision|llava", c[1].name, re.IGNORECASE)
        ]
        if not vision:
            raise BackendNotFoundError("no vision-capable model available")
        chosen_backend, chosen_model, _ = vision[0]
    else:
        candidates.sort(key=lambda x: x[2])
        if category == "small":
            chosen_backend, chosen_model, _ = candidates[0]
        elif category == "large":
            chosen_backend, chosen_model, _ = candidates[-1]
        elif category == "medium":
            chosen_backend, chosen_model, _ = candidates[len(candidates) // 2]
        else:
            raise BackendNotFoundError(
                f"unknown auto category: {target}"
            )

    physical = f"{chosen_backend.alias}/{chosen_model.name}"
    return chosen_backend, chosen_model.name, physical


def _make_default_driver(backend: BackendInfo) -> Driver:
    return Driver(base_url=backend.base_url, api_key=backend.api_key, timeout=60.0)


def _resolve_llm_core_category(
    catalog: BackendCatalog, target: str
) -> tuple[BackendInfo, str, str] | None:
    """Third resolution stage: core/llm_core category registry.

    Looks up ``target`` as an llm_endpoints category. On hit, builds (or
    refreshes) a virtual BackendInfo with ``source="llm_core"`` and returns
    the standard (backend, model_name, physical_id) triple. Returns None when
    the category is not configured. Raises BackendDisabledError when the
    virtual backend has been administratively disabled.
    """
    try:
        from core.llm_core.registry import get_llm_client
        client = get_llm_client(target)
    except Exception:
        return None

    if client is None:
        return None

    virtual_alias = f"llm_core:{target}"
    physical_id = f"{virtual_alias}/{client.model}"

    existing = catalog.get_backend(virtual_alias)
    # Rebuild when the config changed (base_url swap, model rename, etc.).
    # The disabled flag is preserved by set_backend() on upsert.
    needs_rebuild = (
        existing is None
        or existing.base_url != client.base_url
        or existing.api_key != client.api_key
        or not any(m.name == client.model for m in existing.models)
    )
    if needs_rebuild:
        backend = BackendInfo(
            alias=virtual_alias,
            base_url=client.base_url,
            type="openai-compat",
            api_key=client.api_key,
            status="ready",
            auto_discover=False,
            source="llm_core",
            models=[
                ModelInfo(
                    id=physical_id,
                    backend=virtual_alias,
                    name=client.model,
                )
            ],
        )
        catalog.set_backend(backend)
        # set_backend() may have stamped disabled via carry-over or
        # _pending_disabled — re-fetch to honour it below.
        backend = catalog.get_backend(virtual_alias) or backend
    else:
        backend = existing

    if backend.disabled:
        raise BackendDisabledError(backend.alias)

    return backend, client.model, physical_id


def resolve_target(catalog: BackendCatalog, target: str) -> tuple[BackendInfo, str, str]:
    """Resolve a client-facing target string to (backend, model_name, physical_id).

    Resolution order:
        0. auto:* dynamic resolution: "auto:small"/"auto:medium"/"auto:large"/"auto:vision"
        1. Alias map: "local-coder-big" → "ollama-mac/qwen2.5-coder:32b"
        2. Physical name "<backend-alias>/<model-name>"
        3. core/llm_core category registry: "fast"/"large"/"vision" → virtual backend

    Raises BackendNotFoundError on miss, BackendDisabledError if the resolved
    backend is administratively disabled.
    """
    # 0. auto:* dynamic resolution (highest priority)
    if target.startswith("auto:"):
        return _resolve_auto(catalog, target)

    # 1. Alias
    physical = catalog.resolve_alias(target) or target

    # 2. Physical name "<backend-alias>/<model-name>"
    if "/" in physical:
        backend_alias, _, model_name = physical.partition("/")
        backend = catalog.get_backend(backend_alias)
        if backend is not None:
            if backend.disabled:
                raise BackendDisabledError(backend.alias)
            return backend, model_name, physical
        # Fall through to category lookup; an unknown "/" path will simply miss
        # the llm_core registry and produce the canonical not-found error below.

    # 3. llm_core category (pass the original target, not the alias-resolved
    # physical, because categories are flat names like "fast").
    hit = _resolve_llm_core_category(catalog, target)
    if hit is not None:
        return hit

    raise BackendNotFoundError(
        f"target '{target}' is not an alias, physical '<backend>/<model>' name, "
        "or llm_core category"
    )


async def dispatch(
    target: str,
    openai_request: dict,
    stream: bool = False,
    catalog: BackendCatalog | None = None,
    driver_factory: Callable[[BackendInfo], Driver] | None = None,
):
    """Dispatch an OpenAI-format chat request to the resolved backend.

    Returns a dict (non-streaming) or an async iterator of chunk dicts (streaming).
    The model field of openai_request is rewritten to the backend-side model name.
    """
    cat = catalog if catalog is not None else get_catalog()
    factory = driver_factory or _make_default_driver

    backend, model_name, _physical = resolve_target(cat, target)
    drv = factory(backend)

    # Rewrite to backend-side model name
    body = dict(openai_request)
    body["model"] = model_name

    if stream:
        body["stream"] = True
        return drv.chat_stream(body)
    body.pop("stream", None)
    return await drv.chat(body)
