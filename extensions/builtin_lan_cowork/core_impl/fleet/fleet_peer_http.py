"""Shared peer-to-peer HTTP helpers for fleet operations."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def build_peer_headers(
    mgr,
    peer,
    *,
    requested_with: str,
    method: str,
    full_path: str,
    query_string: str = "",
    body: bytes = b"",
    include_accept_sse: bool = False,
) -> dict:
    """Build authenticated and signed headers for peer requests."""
    from core.crypto_identity import path_requires_nonce
    from extensions.builtin_lan_cowork.core_impl.peer_auth_client import (
        build_peer_headers as _signed_headers,
    )

    token = getattr(peer, "token", None)
    headers = _signed_headers(
        mgr.local_seed(),
        mgr.local_peer.peer_id,
        token or "",
        method,
        full_path,
        query_string,
        body,
        require_nonce=path_requires_nonce(full_path),
    )
    headers["X-Requested-With"] = requested_with
    if include_accept_sse:
        headers["Accept"] = "text/event-stream"
    return headers


def get_peer_or_raise(mgr, peer_id: str):
    peer = mgr.registry.get(peer_id)
    if peer is None:
        raise ValueError(f"peer {peer_id} not found")
    return peer


async def fetch_peer_uptime(mgr, peer) -> int | None:
    path = "/ext/lan_cowork/fleet/info"
    headers = build_peer_headers(mgr, peer, requested_with="RestartDispatchRunner", method="GET", full_path=path)
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return int(resp.json().get("process_uptime_sec") or 0)
    except Exception:
        # An unreachable peer is ordinary on a LAN; debug keeps it out of the
        # way while still being findable.
        logger.debug("uptime probe failed for %s", peer.api_host, exc_info=True)
    return None


async def post_peer_restart(mgr, peer) -> tuple[bool, str | None]:
    path = "/ext/lan_cowork/fleet/restart"
    body = b"{}"
    headers = build_peer_headers(
        mgr, peer, requested_with="RestartDispatchRunner", method="POST", full_path=path, body=body
    )
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=body, headers=headers)
            if resp.status_code != 200:
                return False, f"http_{resp.status_code}"
    except Exception as exc:
        return False, f"post_failed: {exc}"
    return True, None


async def post_peer_update(mgr, peer, *, source: str, branch: str, consent_token: str = "") -> dict:
    path = "/ext/lan_cowork/fleet/update"
    body = _json_body({"source": source, "branch": branch})
    headers = build_peer_headers(mgr, peer, requested_with="DispatchRunner", method="POST", full_path=path, body=body)
    if consent_token:
        headers["X-Consent-Token"] = consent_token
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, content=body, headers=headers)
        try:
            return resp.json()
        except Exception:
            return {"error": f"http_{resp.status_code}"}


async def poll_peer_update_job(mgr, peer, *, job_id: str, timeout: float) -> dict:
    path = "/ext/lan_cowork/fleet/update/status"
    query_string = f"job_id={job_id}"
    headers = build_peer_headers(
        mgr,
        peer,
        requested_with="DispatchRunner",
        method="GET",
        full_path=path,
        query_string=query_string,
    )
    base = f"http://{peer.api_host}:{peer.api_port}{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        async with asyncio.timeout(timeout):
            while True:
                try:
                    resp = await client.get(f"{base}?job_id={job_id}", headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") in ("success", "failed"):
                            return data
                except Exception:
                    logger.debug("job poll failed for %s", job_id, exc_info=True)
                await asyncio.sleep(5)


async def proxy_allowlist_to_peer(mgr, peer, *, action: str, categories: list[str]) -> tuple[dict, int]:
    if action not in ("grant", "revoke"):
        return {"ok": False, "error": "invalid action"}, 400
    token = getattr(peer, "token", None)
    if not token:
        return {"ok": False, "error": "no_pairing_token", "message": "peer has no pairing token"}, 409
    path = f"/ext/lan_cowork/fleet/allowlists/{action}"
    body = _json_body({"categories": categories})
    headers = build_peer_headers(mgr, peer, requested_with="FleetPeerGrant", method="POST", full_path=path, body=body)
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, content=body, headers=headers)
            try:
                return resp.json(), resp.status_code
            except Exception:
                return {"ok": False, "error": f"http_{resp.status_code}"}, resp.status_code
    except Exception as exc:
        return {"ok": False, "error": "peer_unreachable", "message": str(exc)}, 502


async def fetch_peer_allowlist_status(mgr, peer) -> tuple[dict, int]:
    token = getattr(peer, "token", None)
    if not token:
        return {"ok": False, "error": "no_pairing_token"}, 409
    path = "/ext/lan_cowork/fleet/allowlists/check"
    headers = build_peer_headers(mgr, peer, requested_with="FleetPeerStatus", method="GET", full_path=path)
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            try:
                return resp.json(), resp.status_code
            except Exception:
                return {"ok": False, "error": f"http_{resp.status_code}"}, resp.status_code
    except Exception as exc:
        return {"ok": False, "reachable": False, "error": "peer_unreachable", "message": str(exc)}, 200


async def relay_consent_request(mgr, peer, *, request_id: str) -> tuple[dict, int]:
    path = "/ext/lan_cowork/fleet/consent/request"
    body = _json_body({"request_id": request_id})
    headers = build_peer_headers(mgr, peer, requested_with="ConsentRelay", method="POST", full_path=path, body=body)
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=body, headers=headers)
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        return body, resp.status_code
    except Exception as exc:
        return {"error": "relay_failed", "detail": str(exc)}, 502


async def relay_consent_status(mgr, peer, *, request_id: str) -> tuple[dict, int]:
    path = f"/ext/lan_cowork/fleet/consent/status/{request_id}"
    headers = build_peer_headers(mgr, peer, requested_with="ConsentRelayStatus", method="GET", full_path=path)
    url = f"http://{peer.api_host}:{peer.api_port}{path}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"error": f"http_{resp.status_code}"}
        return body, resp.status_code
    except Exception as exc:
        return {"error": "relay_failed", "detail": str(exc)}, 502
