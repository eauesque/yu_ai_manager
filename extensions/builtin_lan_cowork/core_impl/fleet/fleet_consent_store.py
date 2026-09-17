"""In-memory consent state and helpers for fleet update approval."""
from __future__ import annotations

import asyncio
import time

# ConsentStore — in-memory, single-worker process local
_consent_store: dict[str, dict] = {}
# { request_id: { chief_peer_id, expires_at, decision, permanent, decided_at } }

_deny_cooldown: dict[str, float] = {}
# { chief_peer_id: cooldown_expires_at }

_consent_lock = asyncio.Lock()


async def consume_consent_token(request_id: str, chief_peer_id: str) -> bool:
    """Atomically consume a one-time approved consent token."""
    async with _consent_lock:
        entry = _consent_store.get(request_id)
        if not entry:
            return False
        if entry.get("decision") != "approved":
            return False
        if entry.get("chief_peer_id") != chief_peer_id:
            return False
        if time.time() > entry.get("expires_at", 0):
            return False
        del _consent_store[request_id]
        return True


async def run_consent_janitor_once() -> None:
    """Single GC pass removing expired consent state and cooldowns."""
    now = time.time()
    to_delete = []
    async with _consent_lock:
        for rid, entry in list(_consent_store.items()):
            decision = entry.get("decision")
            expires_at = entry.get("expires_at", 0)
            decided_at = entry.get("decided_at")

            if decision is None and now > expires_at or decision is not None and decided_at is not None and now > decided_at + 60:
                to_delete.append(rid)

        for rid in to_delete:
            _consent_store.pop(rid, None)

    expired_peers = [p for p, exp in list(_deny_cooldown.items()) if now > exp]
    for p in expired_peers:
        _deny_cooldown.pop(p, None)
