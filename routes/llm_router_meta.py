"""LLM Router meta endpoints: /models, /router/health, /router/refresh, /router/estimate, /router/capabilities."""

from __future__ import annotations

import json
import logging

from quart import Response, request

from core.gateway.auth import get_auth
from core.gateway.errors import openai_error as _gw_error
from core.gateway.scopes import Scope
from core.llm_router import dispatch as dispatch_mod
from core.llm_router.errors import BackendNotFoundError
from core.llm_router.state import get_catalog
from routes.llm_router import _openai_error, bp

logger = logging.getLogger("routes.llm_router")


def _require_scope(scope: Scope):
    """No-op without request._gw_auth; intended only for bp routes after before_request auth."""
    gw_auth = getattr(request, "_gw_auth", None)
    if gw_auth is not None and not get_auth().has_scope(gw_auth, scope):
        return _gw_error("Insufficient scope", "insufficient_scope", 403, param=str(scope))
    return None


@bp.route("/models", methods=["GET"])
async def list_models():
    from core.gateway.auth import GatewayAuth, get_auth
    from core.gateway.errors import openai_error as _gw_error
    from core.gateway.scopes import Scope

    _gw_auth = get_auth()
    _h = request.headers.get("Authorization", "")
    _token = _h[len("Bearer "):] if _h.startswith("Bearer ") else request.headers.get("x-api-key") or None
    _result = _gw_auth.check_request(bearer=_token, remote_addr=request.remote_addr or "")
    if _result is None:
        return _gw_error("Unauthorized", "invalid_api_key", 401, "authentication_error")
    if not GatewayAuth.has_scope(_result, Scope.LLM_MODELS):
        return _gw_error("Insufficient scope", "insufficient_scope", 403, param=str(Scope.LLM_MODELS))

    cat = get_catalog()
    data: list[dict] = []
    # Auto dynamic aliases (virtual models resolved at dispatch time)
    for _cat in ("small", "medium", "large", "vision"):
        resolved_to = None
        try:
            _, _, _physical = dispatch_mod.resolve_target(cat, f"auto:{_cat}")
            resolved_to = _physical
        except Exception as e:
            logger.warning("[list_models] auto:%s resolve failed: %s", _cat, e)
        data.append(
            {
                "id": f"auto:{_cat}",
                "object": "model",
                "owned_by": "router",
                "yu_metadata": {
                    "type": "auto",
                    "category": _cat,
                    "resolved_to": resolved_to,
                },
            }
        )
    # Physical models
    for backend in cat.list_backends():
        for m in backend.models:
            data.append(
                {
                    "id": m.id,
                    "object": "model",
                    "owned_by": backend.alias,
                    "yu_metadata": {
                        "context_window": m.context_window,
                        "size_b": m.size_b,
                        "type": "physical",
                        "backend_status": backend.status,
                        "slo_state": backend.slo_state,
                    },
                }
            )
    # Aliases
    for alias_name, target in cat.list_aliases().items():
        data.append(
            {
                "id": alias_name,
                "object": "model",
                "owned_by": "alias",
                "yu_metadata": {"type": "alias", "target": target},
            }
        )
    # llm_core categories (Phase 2): surface configured llm_endpoints so
    # clients can pick a category like "fast" without knowing the physical
    # backend. Virtual backends are created lazily on dispatch, so we read
    # the live config here instead of relying on catalog state.
    try:
        from core.llm_core.registry import get_llm_client
        from core.services_core.db_state import get_config
        endpoints = (get_config() or {}).get("llm_endpoints") or {}
    except Exception:
        endpoints = {}
    for category in endpoints:
        client = None
        try:
            client = get_llm_client(category)
        except Exception:
            client = None
        if client is None:
            continue
        virtual_alias = f"llm_core:{category}"
        backend = cat.get_backend(virtual_alias)
        data.append(
            {
                "id": category,
                "object": "model",
                "owned_by": "llm_core",
                "yu_metadata": {
                    "type": "llm_core",
                    "category": category,
                    "target": client.model,
                    "base_url": client.base_url,
                    "disabled": bool(backend.disabled) if backend else False,
                },
            }
        )
    return Response(
        json.dumps({"object": "list", "data": data}, ensure_ascii=False),
        content_type="application/json",
    )


@bp.route("/router/health", methods=["GET"])
async def router_health():
    if err := _require_scope(Scope.LLM_MODELS):
        return err
    cat = get_catalog()
    backends_summary = []
    for backend in cat.list_backends():
        backends_summary.append(
            {
                "alias": backend.alias,
                "status": backend.status,
                "model_count": len(backend.models),
                "last_seen": backend.last_seen_at,
                "slo_state": backend.slo_state,
            }
        )
    return Response(
        json.dumps(
            {
                "router": "ok",
                "version": "1.0.0",
                "backends": backends_summary,
                "alias_count": len(cat.list_aliases()),
            },
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/router/refresh", methods=["POST"])
async def router_refresh():
    """Force a fresh /v1/models poll for one or all backends.

    Body: {"backend": "ollama-mac"}  -- optional, omit for all
    """
    from core.llm_router.discovery import discover_all, discover_backend

    if err := _require_scope(Scope.NODE_STATUS):
        return err

    body = await request.get_json(silent=True) or {}
    target_alias = body.get("backend")
    cat = get_catalog()
    if target_alias:
        backend = cat.get_backend(target_alias)
        if backend is None:
            return _openai_error(f"unknown backend: {target_alias}", "not_found", 404)
        await discover_backend(cat, backend)
        return Response(
            json.dumps(
                {
                    "backend": backend.alias,
                    "status": backend.status,
                    "model_count": len(backend.models),
                    "last_error": backend.last_error,
                    "polled_at": backend.last_seen_at,
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        )

    backends = cat.list_backends()
    await discover_all(cat, backends)
    return Response(
        json.dumps(
            {
                "refreshed": [b.alias for b in backends],
            },
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


def _estimate_tokens_tiktoken(messages: list, system: str | None) -> int:
    """Approximate token count using tiktoken cl100k_base."""
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    total = 0
    if system:
        total += len(enc.encode(system))
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += len(enc.encode(block.get("text", "")))
        # Per-message overhead approximation
        total += 4
    return total


@bp.route("/router/estimate", methods=["POST"])
async def router_estimate():
    if err := _require_scope(Scope.LLM_MODELS):
        return err

    body = await request.get_json(silent=True) or {}
    target = body.get("target")
    messages = body.get("messages") or []
    system = body.get("system")
    if not target:
        return _openai_error("target is required", "invalid_request", 400)

    try:
        cat = get_catalog()
        backend, model_name, physical = dispatch_mod.resolve_target(cat, target)
    except BackendNotFoundError as exc:
        return _openai_error(str(exc), "model_not_found", 404)

    model = next((m for m in backend.models if m.name == model_name), None)
    context_window = model.context_window if model and model.context_window else 4096

    estimated = _estimate_tokens_tiktoken(messages, system)
    fits = estimated <= context_window
    return Response(
        json.dumps(
            {
                "target": target,
                "estimated_input_tokens": estimated,
                "context_window": context_window,
                "fits": fits,
                "headroom_tokens": max(0, context_window - estimated),
                "tokenizer": "tiktoken-cl100k-fallback",
            },
            ensure_ascii=False,
        ),
        content_type="application/json",
    )


@bp.route("/router/capabilities/<path:target>", methods=["GET"])
async def router_capabilities(target: str):
    if err := _require_scope(Scope.LLM_MODELS):
        return err

    try:
        cat = get_catalog()
        backend, model_name, physical = dispatch_mod.resolve_target(cat, target)
    except BackendNotFoundError as exc:
        return _openai_error(str(exc), "model_not_found", 404)

    metadata = cat.get_metadata(physical) or {}
    model = next((m for m in backend.models if m.name == model_name), None)

    return Response(
        json.dumps(
            {
                "target": target,
                "physical": physical,
                "context_window": model.context_window if model else None,
                "size_b": model.size_b if model else None,
                "good_at": metadata.get("good_at", []),
                "weak_at": metadata.get("weak_at", []),
                "notes": metadata.get("notes", ""),
                "has_curated_metadata": bool(metadata),
            },
            ensure_ascii=False,
        ),
        content_type="application/json",
    )
