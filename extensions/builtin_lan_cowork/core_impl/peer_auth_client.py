"""PeerAuthClient: local-side pairing + token storage.

Issues pair/request, collects PairingPIN from UI, calls pair/verify,
and stores the raw token into the peers registry.
"""
from __future__ import annotations

import dataclasses
import logging

import httpx

from core.crypto_identity import make_nonce_header, make_signature_headers

from .models import PeerInfo

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_PREFIX = "/ext/lan_cowork"


def build_peer_headers(
    seed: bytes,
    peer_id: str,
    token: str,
    method: str,
    path: str,
    query_string: str,
    body: bytes,
    *,
    require_nonce: bool = False,
) -> dict[str, str]:
    """Build authenticated and signed headers for an outbound peer request."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Peer-Id": peer_id,
        "X-Requested-With": "PeerTransport",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.update(make_signature_headers(seed, method, path, query_string, body))
    if require_nonce:
        headers.update(make_nonce_header())
    return headers


class PeerAuthClient:
    def __init__(self, registry, local_peer) -> None:
        self._registry = registry
        self._local = local_peer
        self._pending_nonce = b""

    async def request_pairing(self, peer: PeerInfo) -> tuple[bool, str | None, str | None, str]:
        """POST /api/peer/pair/request to remote; return (ok, request_id, sas, error_msg)."""
        import base64

        from core.crypto_identity import make_pairing_commit

        url = f"http://{peer.api_host}:{peer.api_port}{_PREFIX}/api/peer/pair/request"
        commit, nonce = make_pairing_commit(self._local.pubkey, self._local.x25519_pk)
        self._pending_nonce = nonce
        payload = {
            "peer_id": self._local.peer_id,
            "host": self._local.api_host,
            "port": self._local.api_port,
            "pubkey": base64.b64encode(self._local.pubkey).decode(),
            "x25519_pk": base64.b64encode(self._local.x25519_pk).decode(),
            "commit": base64.b64encode(commit).decode(),
        }
        # X-Requested-With is required to satisfy the CSRF check on the remote host.
        headers = {"X-Requested-With": "XMLHttpRequest"}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                resp = await c.post(url, json=payload, headers=headers)
                data = resp.json() if resp.content else {}
                if resp.status_code in (200, 202) and data.get("ok"):
                    return True, data.get("request_id"), data.get("sas"), ""
                return False, None, None, data.get("error") or f"HTTP {resp.status_code}"
        except Exception as exc:
            logger.warning("pair/request to %s failed: %s", url, exc)
            return False, None, None, str(exc)

    async def verify_pin(self, peer: PeerInfo, request_id: str, pin: str) -> tuple[bool, str]:
        """POST /api/peer/pair/verify to remote; on success, store token into registry."""
        import base64

        from core.crypto_identity import encrypt_pairing_bundle

        url = f"http://{peer.api_host}:{peer.api_port}{_PREFIX}/api/peer/pair/verify"
        bundle = encrypt_pairing_bundle(
            pin,
            request_id,
            self._local.pubkey,
            self._local.x25519_pk,
            self._pending_nonce,
        )
        payload = {
            "request_id": request_id,
            "encrypted_bundle": base64.b64encode(bundle).decode(),
        }
        # X-Requested-With is required to satisfy the CSRF check on the remote host.
        headers = {"X-Requested-With": "XMLHttpRequest"}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
                resp = await c.post(url, json=payload, headers=headers)
                data = resp.json() if resp.content else {}
                if resp.status_code == 200 and data.get("ok"):
                    import time as _t
                    # Use dataclasses.replace so upsert receives a new object — otherwise
                    # _needs_persist() compares the same reference and skips DB persistence.
                    updated = dataclasses.replace(
                        peer,
                        token=data["token"],
                        token_expires_at=int(data["expires_at"]),
                        token_issued_at=int(_t.time()),
                        pubkey=base64.b64decode(data["server_pubkey"]),
                        x25519_pk=base64.b64decode(data["server_x25519_pk"]),
                    )
                    self._registry.upsert(updated)
                    return True, ""
                return False, data.get("error") or f"HTTP {resp.status_code}"
        except Exception as exc:
            logger.warning("pair/verify to %s failed: %s", url, exc)
            return False, str(exc)

    def invalidate_token(self, peer_id: str) -> None:
        """Clear stored token for a peer (called on 401 from remote)."""
        peer = self._registry.get(peer_id)
        if peer is None:
            return
        # Use dataclasses.replace so _needs_persist() detects the change and writes to DB.
        updated = dataclasses.replace(peer, token=None, token_expires_at=None, token_issued_at=None)
        self._registry.upsert(updated)
        try:
            from core.event_bus import emit
            emit("peer.token_revoked", {"peer_id": peer_id})
        except Exception:
            logger.warning("revocation notice for %s was not emitted", peer_id, exc_info=True)
