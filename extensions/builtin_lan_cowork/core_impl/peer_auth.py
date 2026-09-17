"""Peer API authentication: Ed25519 request signature + Bearer token."""

from __future__ import annotations

import asyncio
import functools
import logging

from quart import jsonify, request

from core.crypto_identity import (
    NonceResult,
    NonceStore,
    path_requires_nonce,
    verify_request_signature,
)

logger = logging.getLogger(__name__)

# NOTE: _PUBLIC_PATHS is intentionally not used inside require_peer_auth.
# Public endpoints are handled by simply *not* applying the @_auth decorator
# in peer_api.py, so this set serves only as documentation of which paths
# are considered unauthenticated.
_PUBLIC_PATHS = frozenset({
    "/api/peer/status",
    "/api/peer/register",
    "/api/peer/discover",
    "/api/peer/pair/request",
    "/api/peer/pair/verify",
})

_nonce_store = NonceStore()
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _nonce_response(nonce_result: NonceResult):
    if nonce_result is NonceResult.GRACE:
        return jsonify({"ok": False, "error": "nonce grace period"}), 503
    return jsonify({"ok": False, "error": "nonce rejected"}), 401


async def _verify_signature_and_optional_nonce(peer, *, require_nonce: bool):
    body = await request.get_data()
    if not verify_request_signature(
        peer.pubkey,
        request.method,
        request.path,
        request.query_string.decode("utf-8"),
        body,
        request.headers.get("X-Peer-Ts", ""),
        request.headers.get("X-Peer-Sig", ""),
    ):
        return jsonify({"ok": False, "error": "signature invalid"}), 401

    if require_nonce:
        nonce = request.headers.get("X-Peer-Nonce", "")
        try:
            ts = int(request.headers.get("X-Peer-Ts", "0") or "0")
        except ValueError:
            ts = 0
        if not nonce:
            return jsonify({"ok": False, "error": "missing nonce"}), 401
        nonce_result = _nonce_store.check_and_store(nonce, ts)
        if nonce_result is not NonceResult.ACCEPTED:
            return _nonce_response(nonce_result)
    return None


def _lookup_peer_or_response(mgr, *, unknown_status: int = 403):
    peer_id = request.headers.get("X-Peer-Id", "").strip()
    if not peer_id:
        return None, None, (jsonify({"ok": False, "error": "missing X-Peer-Id"}), 401)
    peer = mgr.registry.get(peer_id)
    if peer is None:
        return peer_id, None, (jsonify({"ok": False, "error": "unknown peer"}), unknown_status)
    if not peer.pubkey:
        return peer_id, peer, (jsonify({"ok": False, "error": "peer not paired"}), 403)
    return peer_id, peer, None


def _warn_if_write_without_nonce_requirement(path: str, method: str, require_nonce: bool) -> None:
    if require_nonce or method.upper() not in _WRITE_METHODS:
        return
    logger.warning("peer auth write endpoint without nonce requirement: method=%s path=%s", method, path)


async def authenticate_peer_request(mgr):
    """Authenticate the current signed peer request with an active Bearer token."""
    peer_id, peer, err = _lookup_peer_or_response(mgr)
    if err is not None:
        return err

    require_nonce = path_requires_nonce(request.path)
    _warn_if_write_without_nonce_requirement(request.path, request.method, require_nonce)

    err = await _verify_signature_and_optional_nonce(peer, require_nonce=require_nonce)
    if err is not None:
        return err

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"ok": False, "error": "missing token"}), 401
    token = auth[len("Bearer "):].strip()
    verify = mgr.token_store.verify
    if bool(getattr(mgr.token_store, "threadsafe_provider", False)):
        valid = await asyncio.to_thread(verify, peer_id, token)
    else:
        valid = verify(peer_id, token)
    if not valid:
        logger.warning("peer request rejected path=%s", request.path)
        return jsonify({"ok": False, "error": "invalid token"}), 401
    return None


def require_peer_auth(get_manager):
    """Require peer identity signature plus active Bearer token."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            mgr = get_manager()
            if mgr is None:
                return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

            err = await authenticate_peer_request(mgr)
            if err is not None:
                return err

            return await fn(*args, **kwargs)

        return wrapper

    return decorator


def require_peer_renew_auth(get_manager):
    """Require peer identity signature + nonce for token renewal without Bearer."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            mgr = get_manager()
            if mgr is None:
                return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

            _peer_id, peer, err = _lookup_peer_or_response(mgr, unknown_status=404)
            if err is not None:
                return err

            err = await _verify_signature_and_optional_nonce(peer, require_nonce=True)
            if err is not None:
                return err

            return await fn(*args, **kwargs)

        return wrapper

    return decorator
