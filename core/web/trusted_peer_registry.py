"""LAN-trusted-peer auth bypass registry.

Module-level singleton holding the IPs we trust for /ext/<name>/v1/*
extension API access without PIN auth. Populated by the LLM Router
mDNS bridge on peer verify (see core/llm_router/mdns_integration.py),
seeded at init with loopback addresses for self-probe.

Thread-safe: a single lock guards both _ips and _by_node mutations.
Loopback seeds are never removed.

Spec: docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

logger = logging.getLogger("core.web.trusted_peer_registry")

# Both IPv4 and IPv6 loopback. Bypass is always allowed for these so the
# LLM Router self-probe of hailo-local works even when the user has
# enabled quick_lock or has not set a PIN at all.
_LOOPBACK_SEEDS: tuple[str, ...] = ("127.0.0.1", "::1")


class TrustedPeerRegistry:
    """In-memory IP allowlist for /ext/<name>/v1/* peer requests."""

    def __init__(self) -> None:
        self._ips: set[str] = set(_LOOPBACK_SEEDS)
        self._by_node: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def add_peer(self, node_id: str, addresses: Iterable[str]) -> None:
        """Trust all advertised addresses of a verified peer.

        Idempotent: re-adding the same peer overwrites its address set.
        Empty / blank addresses are filtered. If no addresses survive
        the filter, the call is a no-op (logged at debug level).
        """
        if not node_id:
            logger.warning(
                "[trusted_peer] add_peer called with empty node_id — skipping"
            )
            return
        addrs = {a for a in addresses if a}
        if not addrs:
            logger.debug(
                "[trusted_peer] skip add_peer node_id=%s — no addresses",
                node_id[:8],
            )
            return
        with self._lock:
            self._by_node[node_id] = addrs
            self._ips.update(addrs)
        logger.info(
            "[trusted_peer] trusted node=%s addresses=%s",
            node_id[:8],
            sorted(addrs),
        )

    def remove_peer(self, node_id: str) -> bool:
        """Revoke trust for a previously added peer.

        Currently unused at runtime — added as a stub so future TTL or
        explicit-revoke work has a stable API surface. The loopback
        seeds are never removed.

        Returns True if the node existed (and was removed), False if no
        such node_id was registered. When the same IP was advertised by
        multiple nodes, removing one node does NOT yank the IP from the
        trust set; we recompute _ips from the remaining nodes + seeds
        so other nodes' trust is preserved.
        """
        if not node_id:
            logger.warning(
                "[trusted_peer] remove_peer called with empty node_id — skipping"
            )
            return False
        with self._lock:
            addrs = self._by_node.pop(node_id, None)
            if addrs is None:
                return False
            self._ips = set(_LOOPBACK_SEEDS)
            for remaining in self._by_node.values():
                self._ips.update(remaining)
        logger.info(
            "[trusted_peer] revoked node=%s",
            node_id[:8],
        )
        return True

    def contains(self, addr: str) -> bool:
        """Is this remote IP currently trusted? Empty string returns False."""
        if not addr:
            return False
        with self._lock:
            return addr in self._ips

    def is_loopback(self, addr: str) -> bool:
        """Is this address one of the always-trusted loopback seeds?

        Used by auth_chain.check_trusted_peer to decide whether quick_lock
        should be bypassed (loopback yes, peer no).
        """
        return addr in _LOOPBACK_SEEDS

    def list_all(self) -> list[str]:
        """Return a sorted snapshot of every trusted IP. Used by debug API."""
        with self._lock:
            return sorted(self._ips)


_registry = TrustedPeerRegistry()


def get_registry() -> TrustedPeerRegistry:
    """Process-wide singleton accessor."""
    return _registry
