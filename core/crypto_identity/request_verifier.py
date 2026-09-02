"""Server-side request signature verification + nonce replay protection."""
from __future__ import annotations

import base64
import enum
import time
from collections.abc import Callable

from .keypair import verify
from .request_signer import build_canonical_message

REQUEST_TIMESTAMP_TOLERANCE = 30  # seconds


class NonceResult(enum.Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    GRACE = "grace"


def verify_request_signature(
    pubkey: bytes,
    method: str,
    path: str,
    query_string: str,
    body: bytes,
    ts_header: str,
    sig_header: str,
    *,
    tolerance_seconds: int = REQUEST_TIMESTAMP_TOLERANCE,
) -> bool:
    """Verify X-Peer-Ts window + X-Peer-Sig Ed25519 signature."""
    try:
        ts = int(ts_header)
    except (ValueError, TypeError):
        return False
    if abs(int(time.time()) - ts) > tolerance_seconds:
        return False
    try:
        sig = base64.urlsafe_b64decode(sig_header)
    except (ValueError, TypeError):
        return False
    canonical = build_canonical_message(method, path, query_string, ts_header, body)
    return verify(pubkey, canonical, sig)


class NonceStore:
    """In-memory nonce dedup with a startup grace period.

    On restart the in-memory record is empty, which would allow a replay within
    the timestamp window. The grace period rejects all nonce-bearing requests
    for grace_seconds after startup, structurally eliminating that window.
    """

    def __init__(self, grace_seconds: int = REQUEST_TIMESTAMP_TOLERANCE * 2) -> None:
        self._started_at = time.time()
        self._grace_seconds = grace_seconds
        self._seen: dict[str, int] = {}  # nonce -> expiry_ts

    def _evict_expired(self, now: int) -> None:
        expired = [n for n, exp in self._seen.items() if exp <= now]
        for n in expired:
            self._seen.pop(n, None)

    def check_and_store(self, nonce: str, ts: int) -> NonceResult:
        """Return nonce replay state. Rejects all nonce-bearing requests during grace."""
        now = time.time()
        if now - self._started_at < self._grace_seconds:
            return NonceResult.GRACE
        now_i = int(now)
        self._evict_expired(now_i)
        expiry = ts + REQUEST_TIMESTAMP_TOLERANCE * 2
        if expiry <= now_i:
            return NonceResult.DUPLICATE
        if nonce in self._seen:
            return NonceResult.DUPLICATE
        self._seen[nonce] = expiry
        return NonceResult.ACCEPTED


def require_peer_signature(
    get_pubkey_fn: Callable[[str], bytes | None],
    *,
    nonce_store: NonceStore | None = None,
):
    """Quart decorator factory: verify X-Peer-Ts/X-Peer-Sig (+ nonce if store given).

    NOTE: peer_auth.py composes this verification inline rather than using this
    decorator directly, since it also handles X-Peer-Id lookup and Bearer token.
    This decorator is provided for Phase 3 reuse (Mesh / LAN Share).
    """
    import functools

    from quart import request

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            from quart import jsonify

            peer_id = request.headers.get("X-Peer-Id", "").strip()
            pubkey = get_pubkey_fn(peer_id) if peer_id else None
            if pubkey is None:
                return jsonify({"ok": False, "error": "unknown peer"}), 403
            body = await request.get_data()
            ok = verify_request_signature(
                pubkey,
                request.method,
                request.path,
                request.query_string.decode("utf-8"),
                body,
                request.headers.get("X-Peer-Ts", ""),
                request.headers.get("X-Peer-Sig", ""),
            )
            if not ok:
                return jsonify({"ok": False, "error": "signature invalid"}), 401
            if nonce_store is not None:
                nonce = request.headers.get("X-Peer-Nonce", "")
                ts = int(request.headers.get("X-Peer-Ts", "0") or "0")
                if not nonce:
                    return jsonify({"ok": False, "error": "nonce rejected"}), 401
                nonce_result = nonce_store.check_and_store(nonce, ts)
                if nonce_result is NonceResult.GRACE:
                    return jsonify({"ok": False, "error": "nonce grace period"}), 503
                if nonce_result is NonceResult.DUPLICATE:
                    return jsonify({"ok": False, "error": "nonce rejected"}), 401
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
