"""Admin Blueprint for the LLM Router WebUI.

Exposes a small set of /api/llm_router/* endpoints behind the normal yu_ai_manager
web auth chain (PIN/session). Distinct from the OpenAI-compatible /v1/* surface,
which has its own loopback/api_key auth and must not be polluted with admin
write operations.
"""

from __future__ import annotations

import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from core.llm_router.state import get_catalog

logger = logging.getLogger("routes.llm_router_admin")

bp = Blueprint("llm_router_admin", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _serialize_backend(backend) -> dict:
    """Convert a BackendInfo into the JSON shape the WebUI expects.

    The shape is intentionally a small projection of BackendInfo so that
    future fields can be added internally without leaking everything to
    the client.
    """
    return {
        "alias": backend.alias,
        "base_url": backend.base_url,
        "source": backend.source,
        "status": backend.status,
        "slo_state": backend.slo_state,
        "disabled": backend.disabled,
        "model_count": len(backend.models),
        "models": [
            {
                "name": m.name,
                "context_window": m.context_window,
                "size_b": m.size_b,
            }
            for m in backend.models
        ],
        "last_seen": backend.last_seen_at,
        "last_error": backend.last_error,
    }


# NOTE: this admin surface uses a data-nested envelope (payload wraps its
# body in {"data": {...}}) rather than the flatter {"status": ...} pattern
# used by routes/scheduler_api.py. Tasks 9 and 10 should stay consistent
# with this convention so the client sees a uniform body across all
# /api/llm_router/* endpoints. api_result's internals preserve both keys
# thanks to the body.update(payload) step — see core/infra_core/api_errors.py.
@bp.route("/api/llm_router/status", methods=["GET"])
async def status():
    """Single snapshot used to populate the entire dashboard."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    try:
        cat = get_catalog()
        backends = [_serialize_backend(b) for b in cat.list_backends()]
        aliases = cat.list_aliases()
        return api_result(
            {
                "data": {
                    "router": {
                        "version": "1.0.0",
                        "alias_count": len(aliases),
                    },
                    "backends": backends,
                    "aliases": aliases,
                }
            },
            200,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("[llm_router_admin] failed to build status")
        return api_result({"error": "failed to build status"}, 500)


def _refresh_record(backend) -> dict:
    """Per-backend record returned by /refresh.

    Includes `disabled` so the UI can sync state atomically: a refresh
    that completes after a disable must not visually re-enable the row.
    """
    return {
        "alias": backend.alias,
        "status": backend.status,
        "model_count": len(backend.models),
        "disabled": backend.disabled,
        "last_error": backend.last_error,
    }


@bp.route("/api/llm_router/refresh", methods=["POST"])
async def refresh():
    """Force a fresh probe for one or all backends."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from core.llm_router import discovery as _discovery

    body = await request.get_json(silent=True) or {}
    target_alias = body.get("alias")
    cat = get_catalog()

    if target_alias:
        backend = cat.get_backend(target_alias)
        if backend is None:
            return api_result({"error": f"unknown backend: {target_alias}"}, 404)
        await _discovery.discover_backend(cat, backend)
        # Re-fetch from the catalog (the single source of truth) in case a
        # concurrent probe_loop or mDNS registration overwrote this entry
        # between discover_backend completion and serialization.
        fresh = cat.get_backend(target_alias)
        return api_result(
            {"data": {"refreshed": [_refresh_record(fresh)]}},
            200,
        )

    backends = cat.list_backends()
    await _discovery.discover_all(cat, backends)
    refreshed = [_refresh_record(cat.get_backend(b.alias)) for b in backends]
    return api_result({"data": {"refreshed": refreshed}}, 200)


async def _set_disabled_with_rollback(alias: str, new_value: bool) -> tuple[dict, int]:
    """Toggle disabled, persist, rollback on persistence failure.

    Returns (api_result_payload_dict, http_status). The pattern is extracted
    so disable and enable share identical atomic semantics.

    Atomicity scope: this helper is atomic under Quart/Hypercorn's
    single-worker-per-process model because there is no ``await`` between
    ``cat.set_disabled`` and ``save_disabled_aliases``, so two concurrent
    handlers on the same worker cannot interleave inside the critical
    section. If ``save_disabled_aliases`` is ever wrapped in
    ``asyncio.to_thread(...)`` to stop blocking the event loop, this
    helper MUST be re-guarded by an ``asyncio.Lock`` to preserve the
    rollback invariant against TOCTOU races.

    Exception scope: ``save_disabled_aliases`` performs ``mkdir``,
    ``write_text``, and ``os.replace`` — all of which raise ``OSError``
    subclasses (including ``PermissionError``, ``FileNotFoundError``,
    ``OSError`` for disk-full, etc.). ``json.dumps`` is called on a
    list-of-str that we build ourselves from catalog state, so a
    ``TypeError`` is not reachable without a programming bug elsewhere
    and is allowed to propagate as 500.
    """
    from core.llm_router import persistence as _persistence

    cat = get_catalog()
    backend = cat.get_backend(alias)
    if backend is None:
        return ({"error": f"unknown backend: {alias}"}, 404)

    previous = backend.disabled
    cat.set_disabled(alias, new_value)
    try:
        _persistence.save_disabled_aliases(cat.list_disabled_aliases())
    except OSError as exc:
        # Rollback so in-memory state matches what is on disk.
        cat.set_disabled(alias, previous)
        logger.warning(
            "[llm_router_admin] persist failure for %s, rolling back: %s",
            alias, exc,
        )
        return (
            {"error": "failed to persist disabled state"},
            500,
        )

    return (
        {"data": {"alias": alias, "disabled": new_value}},
        200,
    )


@bp.route("/api/llm_router/backends/<alias>/disable", methods=["POST"])
async def disable_backend(alias: str):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await _set_disabled_with_rollback(alias, True)
    return api_result(payload, status)


@bp.route("/api/llm_router/backends/<alias>/enable", methods=["POST"])
async def enable_backend(alias: str):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await _set_disabled_with_rollback(alias, False)
    return api_result(payload, status)
