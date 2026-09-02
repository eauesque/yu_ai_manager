"""extensions/builtin_lan_cowork/core_impl/transport.py
PeerTransport — HTTP communication layer for peer-to-peer messaging.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .models import PeerInfo, PeerMessage

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds


class PeerTransport:
    """HTTP transport for peer communication."""

    # Blueprint prefix for peer API endpoints
    _PREFIX = "/ext/lan_cowork"

    def __init__(self, local_peer_id: str = "", seed: bytes | None = None) -> None:
        self._local_peer_id = local_peer_id
        self._seed = seed
        # Track consecutive transport-level failures per URL for log suppression
        self._fail_counts: dict[str, int] = {}

    def _full_path(self, path: str) -> str:
        # Prefix peer API paths with the blueprint mount point
        if path.startswith("/api/peer/"):
            return f"{self._PREFIX}{path}"
        return path

    def build_url(self, peer: PeerInfo, path: str) -> str:
        path = self._full_path(path)
        return f"http://{peer.api_host}:{peer.api_port}{path}"

    def build_signed_headers(
        self,
        peer: PeerInfo,
        method: str,
        full_path: str,
        body: bytes,
        *,
        query_string: str = "",
        require_nonce: bool = False,
    ) -> dict[str, str]:
        """Build signed peer request headers."""
        if self._seed is None:
            raise RuntimeError("PeerTransport requires a local seed for signed peer requests")
        from .peer_auth_client import build_peer_headers

        token_valid = (
            peer.token
            and (peer.token_expires_at is None or peer.token_expires_at > time.time())
        )
        token = peer.token if token_valid else ""
        return build_peer_headers(
            self._seed,
            self._local_peer_id,
            token,
            method,
            full_path,
            query_string,
            body,
            require_nonce=require_nonce,
        )

    async def send(
        self, peer: PeerInfo, path: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        _401_reason: str = "401_transport",
    ) -> tuple[bool, dict[str, Any]]:
        """Send an HTTP request to a peer. Returns (success, response_data)."""
        import json as _json

        import httpx

        from core.crypto_identity import path_requires_nonce

        url = self.build_url(peer, path)
        full_path_with_qs = self._full_path(path)
        full_path, _, query_string = full_path_with_qs.partition("?")
        body_bytes = (
            _json.dumps(data, separators=(",", ":")).encode()
            if data is not None and method in ("POST", "PUT")
            else b""
        )
        headers = self.build_signed_headers(
            peer,
            method,
            full_path,
            body_bytes,
            query_string=query_string,
            require_nonce=path_requires_nonce(full_path),
        )
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                kwargs: dict[str, Any] = {"headers": headers}
                if data is not None and method in ("POST", "PUT"):
                    kwargs["content"] = body_bytes
                resp = await client.request(method, url, **kwargs)
                try:
                    body = resp.json()
                except ValueError:
                    # Empty body or non-JSON (e.g. old peer version); use status code only
                    body = {}
                self._fail_counts.pop(url, None)  # reset on any HTTP response
                # On 401, invalidate the stored token so the next request triggers re-pairing
                # and emit an SSE event so the UI can show a re-pair badge.
                if resp.status_code == 401:
                    logger.warning(
                        "PeerTransport.send 401 Unauthorized from peer %s, invalidating token",
                        peer.peer_id,
                    )
                    try:
                        from ..lan_cowork_ext import _get_manager
                        mgr = _get_manager()
                        if mgr is not None and hasattr(mgr, "auth_client"):
                            mgr.auth_client.invalidate_token(peer.peer_id)
                    except Exception as _e:
                        logger.debug("Could not invalidate token for %s: %s", peer.peer_id, _e)
                    try:
                        from core.event_bus import emit
                        from core.event_bus.event_types import PEER_AUTH_LOST
                        emit(PEER_AUTH_LOST, {
                            "peer_id": peer.peer_id,
                            "reason": _401_reason,
                        }, source="lan-cowork")
                    except Exception as _e:
                        logger.debug("Could not emit PEER_AUTH_LOST for %s: %s", peer.peer_id, _e)
                ok = resp.status_code < 400
                if not ok:
                    # Surface status + body so upstream can construct a useful error message
                    body = dict(body)
                    body.setdefault("error", f"HTTP {resp.status_code}")
                    body["status"] = resp.status_code
                    logger.warning(
                        "PeerTransport.send %s %s -> HTTP %d body=%s",
                        method, url, resp.status_code, body,
                    )
                return ok, body
        except Exception as e:
            count = self._fail_counts.get(url, 0) + 1
            self._fail_counts[url] = count
            # Log first failure and every 6th (≈ 1 min at 10s heartbeat) to avoid flooding
            # Some httpx errors stringify to "" — use repr() so the exception
            # type is always visible (e.g. ConnectError, ReadTimeout).
            err_str = str(e) or repr(e)
            if count == 1 or count % 6 == 0:
                logger.warning("PeerTransport.send to %s failed: %s", url, err_str)
            else:
                logger.debug("PeerTransport.send to %s failed (x%d): %s", url, count, err_str)
            return False, {"error": err_str}

    async def send_message(self, peer: PeerInfo, message: PeerMessage) -> tuple[bool, dict[str, Any]]:
        return await self.send(peer, "/api/peer/message", message.to_dict())

    async def heartbeat(self, peer: PeerInfo, local_info: dict[str, Any]) -> bool:
        ok, _ = await self.send(
            peer, "/api/peer/heartbeat", local_info,
            _401_reason="401_heartbeat",
        )
        return ok

    async def fetch_json(self, peer: PeerInfo, path: str) -> tuple[bool, dict[str, Any]]:
        return await self.send(peer, path, method="GET")
