"""extensions/builtin_lan_cowork/core_impl/registry.py
PeerRegistry — thread-safe peer list management with selection logic.
"""
from __future__ import annotations

import json
import threading
import time

from .models import PeerInfo


class PeerRegistry:
    """Manages known peers and provides selection for job dispatch."""

    def __init__(self, offline_timeout: float = 30.0, local_peer_id: str | None = None) -> None:
        self._peers: dict[str, PeerInfo] = {}
        self._pubkey_index: dict[bytes, str] = {}
        self._lock = threading.Lock()
        self._offline_timeout = offline_timeout
        self._local_peer_id = local_peer_id
        self._load_all()

    def upsert(self, peer: PeerInfo) -> None:
        if self._local_peer_id and peer.peer_id == self._local_peer_id:
            return
        with self._lock:
            existing = self._peers.get(peer.peer_id)
            if existing is not None and existing.pubkey and existing.pubkey != peer.pubkey:
                self._pubkey_index.pop(existing.pubkey, None)
            self._peers[peer.peer_id] = peer
            if peer.pubkey:
                self._pubkey_index[peer.pubkey] = peer.peer_id
            persist_needed = self._needs_persist(existing, peer)
        if persist_needed:
            self._persist(peer)

    def update_runtime(
        self,
        peer_id: str,
        *,
        generating: bool | None = None,
        queue_depth: int | None = None,
        bridges: list[str] | None = None,
        inference_types: list[str] | None = None,
        last_seen: float | None = None,
        status: str | None = None,
    ) -> PeerInfo | None:
        """Update in-memory runtime state without touching persistent peer fields."""
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer is None:
                return None
            if generating is not None:
                peer.generating = generating
            if queue_depth is not None:
                peer.queue_depth = queue_depth
            if bridges is not None:
                peer.bridges = bridges
            if inference_types is not None:
                peer.inference_types = inference_types
            if last_seen is not None:
                peer.last_seen = last_seen
            if status is not None:
                peer.status = status
            return peer

    def get(self, peer_id: str) -> PeerInfo | None:
        with self._lock:
            return self._peers.get(peer_id)

    def get_by_pubkey(self, pubkey: bytes) -> PeerInfo | None:
        """Look up a peer by its Ed25519 pubkey."""
        with self._lock:
            peer_id = self._pubkey_index.get(pubkey)
            return self._peers.get(peer_id) if peer_id else None

    def remove(self, peer_id: str) -> None:
        with self._lock:
            existing = self._peers.pop(peer_id, None)
            if existing is not None and existing.pubkey:
                self._pubkey_index.pop(existing.pubkey, None)
        try:
            from core.services_core.peer_registry_service import delete_peer_record

            delete_peer_record(peer_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("delete peer failed: %s", exc)

    def list_all(self) -> list[PeerInfo]:
        with self._lock:
            return list(self._peers.values())

    def list_online(self) -> list[PeerInfo]:
        with self._lock:
            return [p for p in self._peers.values() if p.status == "online"]

    def check_timeouts(self) -> list[str]:
        """Mark peers as offline if last_seen exceeds timeout.
        Returns list of peer_ids that went offline."""
        now = time.time()
        went_offline: list[str] = []
        with self._lock:
            for p in self._peers.values():
                if p.status == "online" and (now - p.last_seen) > self._offline_timeout:
                    p.status = "offline"
                    went_offline.append(p.peer_id)
        return went_offline

    def _persist(self, peer: PeerInfo) -> None:
        """Upsert peer row into peers table."""
        try:
            from core.services_core.peer_registry_service import upsert_peer_record

            upsert_peer_record(peer)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("persist peer failed: %s", exc)

    def _load_all(self) -> None:
        """Restore peers from DB into memory on startup.

        Hard-prunes peers whose last successful reach is older than the
        configured retention (default 7 d). DHCP / IP rotation otherwise
        causes unbounded growth in the peers table.
        """
        try:
            import logging as _logging

            from core.services_core.db_state import get_readonly_db
            from core.services_core.peer_registry_service import (
                prune_stale_peers,
                prune_unpaired_unreached_peers,
            )

            from .fleet.fleet_config import (
                DEFAULT_HARD_PRUNE_SEC,
                DEFAULT_SOFT_PRUNE_SEC,
            )
            from .models import PeerInfo

            cutoff = int(time.time()) - DEFAULT_HARD_PRUNE_SEC
            pruned: list[str] = []
            try:
                pruned = prune_stale_peers(cutoff)
                if pruned:
                    _logging.getLogger(__name__).info(
                        "PeerRegistry: hard-pruned %d stale peer(s) on load (cutoff=%ds)",
                        len(pruned),
                        DEFAULT_HARD_PRUNE_SEC,
                    )
            except Exception as exc:
                _logging.getLogger(__name__).warning("hard-prune failed: %s", exc)

            soft_cutoff = int(time.time()) - DEFAULT_SOFT_PRUNE_SEC
            soft_pruned: list[str] = []
            try:
                soft_pruned = prune_unpaired_unreached_peers(soft_cutoff)
                if soft_pruned:
                    _logging.getLogger(__name__).info(
                        "PeerRegistry: soft-pruned %d unpaired/unreached peer(s)",
                        len(soft_pruned),
                    )
            except Exception as exc:
                _logging.getLogger(__name__).warning("soft-prune failed: %s", exc)

            pruned_ids = set(pruned) | set(soft_pruned)
            con = get_readonly_db()
            rows = con.execute(
                """SELECT peer_id, name, api_host, api_port,
                          token, token_expires_at, token_issued_at,
                          pubkey, x25519_pk, inference_types,
                          last_reached_at, last_attempted_at
                   FROM peers"""
            ).fetchall()
            stale_self = False
            for r in rows:
                if self._local_peer_id and r[0] == self._local_peer_id:
                    stale_self = True
                    continue
                # Skip rows the prune writer is about to delete (the writer
                # is async via submit_db_write_no_wait, so the row may still
                # be visible to this SELECT). Filter on (a) the explicit
                # pruned_ids list — covers hard-pruned rows and soft-pruned
                # unpaired discovery artifacts — and (b) the `last_reached <
                # cutoff` check as a defensive belt-and-suspenders for any
                # future drift in the prune predicate.
                if r[0] in pruned_ids:
                    continue
                last_reached = r[10]
                if last_reached is not None and last_reached < cutoff:
                    continue
                p = PeerInfo(peer_id=r[0], name=r[1] or "", api_host=r[2] or "", api_port=r[3] or 0)
                p.token = r[4]
                p.token_expires_at = r[5]
                p.token_issued_at = r[6]
                p.pubkey = r[7]
                p.x25519_pk = r[8]
                try:
                    inference_types = json.loads(r[9] or "[]")
                    p.inference_types = (
                        inference_types if isinstance(inference_types, list) else []
                    )
                except (TypeError, json.JSONDecodeError):
                    p.inference_types = []
                p.last_reached_at = last_reached
                p.last_attempted_at = r[11]
                self._peers[r[0]] = p
                if p.pubkey:
                    self._pubkey_index[p.pubkey] = p.peer_id
            if stale_self:
                try:
                    from core.services_core.peer_registry_service import cleanup_local_peer_record

                    cleanup_local_peer_record(self._local_peer_id)
                    import logging
                    logging.getLogger(__name__).info(
                        "Removed stale self row from peers table (peer_id=%s)",
                        self._local_peer_id,
                    )
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("cleanup self row failed: %s", exc)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("load peers failed: %s", exc)

    @staticmethod
    def _persistent_snapshot(peer: PeerInfo) -> tuple:
        return (
            peer.name,
            peer.api_host,
            peer.api_port,
            peer.token,
            peer.token_expires_at,
            peer.token_issued_at,
            peer.pubkey,
            peer.x25519_pk,
        )

    def _needs_persist(self, existing: PeerInfo | None, peer: PeerInfo) -> bool:
        if existing is None:
            return True
        return self._persistent_snapshot(existing) != self._persistent_snapshot(peer)

    def select_peer(
        self, bridge: str, exclude_ids: list[str] | None = None,
    ) -> PeerInfo | None:
        """Select the best online peer for a given bridge type.

        Selection: bridge supported -> not generating -> lowest queue_depth -> most recent.
        This is the RuleBasedStrategy — will be swappable for LLM negotiation later.
        """
        exclude = set(exclude_ids or [])
        with self._lock:
            candidates = [
                p for p in self._peers.values()
                if p.status == "online"
                and bridge in p.bridges
                and p.peer_id not in exclude
            ]
        if not candidates:
            return None
        # Prefer non-generating, then lowest queue_depth, then most recently seen
        candidates.sort(key=lambda p: (p.generating, p.queue_depth, -p.last_seen))
        return candidates[0]
