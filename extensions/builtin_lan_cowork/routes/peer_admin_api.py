"""Admin endpoints for peer token management (requires session pin_ok)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from quart import Blueprint, jsonify

from core.web.auth_route_policy import auth_route

logger = logging.getLogger(__name__)

_AUTH_PREFIX = "/ext/lan_cowork"


def register_routes(
    bp: Blueprint,
    *,
    token_store: Callable,
    session_guard: Callable,
    get_manager: Callable | None = None,
) -> None:

    async def _call_store(method_name: str, *args, **kwargs):
        store = token_store()
        if store is None:
            return None, (jsonify({"ok": False, "error": "service unavailable"}), 503)
        method = getattr(store, method_name)
        if getattr(store, "threadsafe_provider", False):
            return await asyncio.to_thread(method, *args, **kwargs), None
        return method(*args, **kwargs), None

    def _clear_registry_token(peer_id: str) -> None:
        """Clear in-memory registry token info so the peer immediately
        appears un-paired in the UI (otherwise stale token_expires_at
        keeps the peer listed as paired until restart / re-discovery)."""
        if get_manager is None:
            return
        mgr = get_manager()
        if mgr is None:
            return
        try:
            registry = getattr(mgr, "registry", None)
            if registry is None:
                return
            peer = registry.get(peer_id)
            if peer is None:
                return
            import dataclasses as _dc
            updated = _dc.replace(
                peer, token=None, token_expires_at=None, token_issued_at=None,
            )
            registry.upsert(updated)
        except Exception:
            # This IS the revocation. The route answers ok either way, so the
            # UI shows the peer un-paired while the registry still holds it.
            logger.error("registry entry for %s was not cleared", peer_id, exc_info=True)

    @auth_route(bp, "/api/peer/tokens", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def list_tokens():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        tokens, err = await _call_store("list_active")
        if err is not None:
            return err
        return jsonify({"ok": True, "tokens": tokens})

    @auth_route(bp, "/api/peer/tokens/<peer_id>/revoke", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def revoke_token(peer_id: str):
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        _, err = await _call_store("revoke", peer_id)
        if err is not None:
            return err
        # Clear in-memory registry token so the peer immediately shows as
        # un-paired in the UI without requiring a refresh wait.
        _clear_registry_token(peer_id)
        try:
            from core.sse.sse_bus import publish
            publish("peer.token_revoked", {"peer_id": peer_id})
        except Exception:
            # Revocation stands; the UI just will not refresh on its own.
            logger.warning("revocation notice for %s was not published", peer_id, exc_info=True)
        return jsonify({"ok": True})
