"""Bridge between mDNS peer events and the LLM Router BackendCatalog.

Verifies every incoming peer via an HTTP call to the peer's
``/api/mdns/identity`` endpoint before touching the catalog, applies a
node_id-keyed cooldown on verification failures, and keeps the catalog in
sync with ``added`` / ``updated`` / ``removed`` mDNS events.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

from core.llm_router.mdns_integration_helpers import (
    apply_peer_to_catalog,
    find_backend,
    mark_unreachable,
    verify_peer,
)
from core.llm_router.models import BackendInfo
from core.llm_router.state import BackendCatalog
from core.mdns.peer_info import PeerInfo

logger = logging.getLogger("core.llm_router.mdns_integration")

COOLDOWN_SECONDS: int = 60  # 1 minute — short enough to recover from a single
# transient verify failure (e.g. cold-start congestion when the peer is busy
# loading models). Was 300s but that was way too long for the common "both
# nodes started within seconds of each other" case.
_VERIFY_TIMEOUT_SEC: float = 10.0  # Cold-start tolerance: a peer that just
# booted may take several seconds to respond while loading CLIP/ONNX/etc.,
# even though /api/mdns/identity is itself a 6ms endpoint. Was 2.0 but that
# tripped on every fresh 2-node startup.
_WAIT_FOR_BUFFER_SEC: float = 2.0  # asyncio.wait_for adds this on top of the
# httpx timeout to absorb scheduling jitter on a busy event loop.
_ALIAS_PREFIX: str = "mdns-"


IdentityVerifier = Callable[[PeerInfo], Awaitable[dict]]


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_verifier() -> IdentityVerifier:
    """Real identity verifier using httpx. Imported lazily.

    NOTE: receives a PeerInfo whose ``addresses`` has been narrowed to a
    single entry by ``LlmRouterMdnsBridge._verify`` — so this verifier
    only needs to attempt one address per call. The bridge iterates and
    calls the verifier repeatedly (once per advertised address) until
    one succeeds, which handles peers that advertise unreachable virtual
    interface addresses (e.g. Windows's WSL/Hyper-V 172.x addresses
    ahead of the real LAN IP).
    """
    import httpx  # noqa: WPS433

    async def verify(peer: PeerInfo) -> dict:
        if not peer.addresses or not peer.web_port:
            raise ValueError("peer has no address or web_port")
        url = f"http://{peer.addresses[0]}:{peer.web_port}/api/mdns/identity"
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT_SEC) as client:
            res = await client.get(url)
            res.raise_for_status()
            return res.json()

    return verify


async def _probe_bare_ollama(peer: PeerInfo) -> str | None:
    from core.llm_endpoint_discovery.probes import probe_ollama_tags

    if not peer.addresses:
        logger.warning("[mdns] bare ollama peer %s has no addresses", peer.node_id[:8])
        return None
    split = urlsplit(peer.llm_base_url)
    for candidate in peer.addresses:
        target = urlunsplit(
            (split.scheme or "http", f"{candidate}:{split.port or 11434}", "", "", "")
        )
        try:
            ok = await asyncio.to_thread(
                probe_ollama_tags,
                target,
                timeout=_VERIFY_TIMEOUT_SEC,
                user_agent="yu_ai_manager/mdns",
            )
        except Exception as exc:
            logger.debug(
                "[mdns] bare ollama probe failed for %s via %s: %s",
                peer.node_id[:8], candidate, exc,
            )
            continue
        if ok:
            return candidate
    logger.warning(
        "[mdns] bare ollama verify failed for %s on all %d addresses",
        peer.node_id[:8], len(peer.addresses),
    )
    return None


class LlmRouterMdnsBridge:
    def __init__(
        self,
        *,
        self_node_id: str,
        verify_identity: IdentityVerifier | None = None,
    ) -> None:
        self._self_node_id = self_node_id
        self._verify_identity = verify_identity or _default_verifier()
        self._catalog: BackendCatalog | None = None
        self._cooldown: dict[str, float] = {}
        self._managed_aliases: set[str] = set()
        self._config_aliases: set[str] = set()

    def attach_catalog(self, catalog: BackendCatalog) -> None:
        self._catalog = catalog

    def mark_config_aliases(self, aliases: Iterable[str]) -> None:
        self._config_aliases = set(aliases)

    async def on_peer_added(self, peer: PeerInfo) -> None:
        if self._in_cooldown(peer.node_id):
            logger.debug("[mdns] skip peer %s in cooldown", peer.node_id[:8])
            return
        verified_addr = await self._verify(peer)
        if verified_addr is None:
            self._enter_cooldown(peer.node_id)
            return
        self._apply_peer_to_catalog(peer, verified_addr)

    async def on_peer_updated(self, peer: PeerInfo) -> None:
        # Intentionally NOT respecting cooldown on update events: a fresh
        # mDNS update means the peer re-advertised (new TXT, address
        # change, restart, etc.), which is exactly the kind of state
        # change that can resolve a previous verify failure. Clearing
        # the cooldown gives the new state a chance. See v4.66.3 race
        # condition debugging (stale TXT version during rolling upgrade).
        self._cooldown.pop(peer.node_id, None)
        verified_addr = await self._verify(peer)
        if verified_addr is None:
            self._enter_cooldown(peer.node_id)
            self._mark_unreachable(peer.node_id, reason="identity verification failed on update")
            return
        self._apply_peer_to_catalog(peer, verified_addr)

    async def on_peer_removed(self, node_id: str) -> None:
        # Clearing the cooldown here ensures a restart → fresh verification
        # cycle works even if the previous attempt was still in the 5-minute
        # window. This is documented in the spec's error table.
        self._cooldown.pop(node_id, None)
        self._mark_unreachable(node_id, reason="mdns service_removed")

    async def retry_pending_peers(self, peers: Iterable[PeerInfo]) -> None:
        """Retry verification for peers not currently reachable in the catalog.

        Called periodically by the startup sweep task to recover from states
        that neither ``on_peer_added`` nor ``on_peer_updated`` can fix on
        their own: a peer that was in cooldown when first discovered, or a
        peer whose TXT change never fired ``ServiceStateChange.Updated``
        (e.g. zeroconf cache quirks during a rolling upgrade).
        Respects active cooldown so genuinely unreachable peers don't
        tight-loop — ``_in_cooldown`` auto-pops expired entries, letting a
        fresh attempt through once the window elapses.
        """
        if self._catalog is None:
            return
        for peer in peers:
            if peer.node_id == self._self_node_id:
                continue
            alias_base = f"{_ALIAS_PREFIX}{peer.node_id[:8]}"
            candidates = (
                alias_base,
                f"{alias_base}-ollama",
                f"{alias_base}-hailo",
                f"{alias_base}-hailo-ollama",
            )
            already_reachable = False
            for a in candidates:
                if a not in self._managed_aliases:
                    continue
                existing = self._find(a)
                if existing is not None and existing.status != "unreachable":
                    already_reachable = True
                    break
            if already_reachable:
                continue
            if self._in_cooldown(peer.node_id):
                continue
            verified_addr = await self._verify(peer)
            if verified_addr is None:
                self._enter_cooldown(peer.node_id)
                continue
            self._apply_peer_to_catalog(peer, verified_addr)
            logger.info(
                "[mdns] sweep re-verified peer %s via %s",
                peer.node_id[:8], verified_addr,
            )

    def _in_cooldown(self, node_id: str) -> bool:
        deadline = self._cooldown.get(node_id)
        if deadline is None:
            return False
        if time.monotonic() >= deadline:
            self._cooldown.pop(node_id, None)
            return False
        return True

    def _enter_cooldown(self, node_id: str) -> None:
        self._cooldown[node_id] = time.monotonic() + COOLDOWN_SECONDS

    async def _verify(self, peer: PeerInfo) -> str | None:
        return await verify_peer(self, peer)

    def _apply_peer_to_catalog(
        self,
        peer: PeerInfo,
        verified_address: str | None = None,
    ) -> None:
        apply_peer_to_catalog(self, peer, verified_address)

    def _mark_unreachable(self, node_id: str, *, reason: str) -> None:
        mark_unreachable(self, node_id, reason=reason)

    def _find(self, alias: str) -> BackendInfo | None:
        return find_backend(self, alias)
