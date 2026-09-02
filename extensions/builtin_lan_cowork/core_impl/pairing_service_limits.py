"""In-memory rate and pending-cap helpers for PairingService."""

from __future__ import annotations

import time
from collections import deque


def enforce_rate_limit(service, source_ip: str) -> None:
    now = time.time()
    dq = service._ip_requests.setdefault(source_ip, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= service._RATE_LIMIT_PER_MIN:
        raise service.RateLimitExceeded(f"rate limit: {service._RATE_LIMIT_PER_MIN}/min")
    dq.append(now)


def enforce_pending_cap(service, source_ip: str) -> None:
    pending_set = service._ip_pending.get(source_ip, set())
    active_ids = set()
    for rid in list(pending_set):
        row = service.get(rid)
        if row and row["status"] in ("pending", "approved"):
            active_ids.add(rid)
    service._ip_pending[source_ip] = active_ids
    if len(active_ids) >= service._PENDING_CAP_PER_IP:
        raise service.PendingCapExceeded(f"pending cap: {service._PENDING_CAP_PER_IP} for {source_ip}")


def remove_from_pending_cap(service, request_id: str) -> None:
    for pending_set in service._ip_pending.values():
        pending_set.discard(request_id)


def sync_pending_cap_after_sweep(service) -> None:
    for source_ip in list(service._ip_pending.keys()):
        active_ids = set()
        for rid in list(service._ip_pending[source_ip]):
            row = service.get(rid)
            if row and row["status"] in ("pending", "approved"):
                active_ids.add(rid)
        service._ip_pending[source_ip] = active_ids
