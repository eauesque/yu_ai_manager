"""FleetManager — chief-side peer info cache and polling."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time

logger = logging.getLogger(__name__)


class FleetManager:
    """Runs on chief node: polls /fleet/info from peers, caches results."""

    def __init__(self, mgr) -> None:
        self._mgr = mgr
        self._cache: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        # Per-peer consecutive failure counter. After this many failures the
        # WARN log is downgraded to DEBUG (the peer is presumed offline; we
        # keep polling for recovery but stop spamming the log).
        self._consecutive_failures: dict[str, int] = {}
        self._noise_threshold = 3

    async def observe_and_maybe_demote(self) -> bool:
        """Observe heartbeats for chief_observation_sec; demote if another chief
        with a lexicographically smaller peer_id is detected.

        Deterministic tiebreaker (smaller peer_id wins) avoids the two-chief
        deadlock where both nodes detect each other and both demote.

        Returns True if demoted, False if local node keeps chief role.
        """
        from .fleet_config import get_fleet_cfg, get_fleet_timings
        fleet_cfg = get_fleet_cfg(self._mgr)
        timings = get_fleet_timings(fleet_cfg)
        observation_sec = timings["chief_observation_sec"]

        start = time.monotonic()
        while time.monotonic() - start < observation_sec:
            existing_chief = self._find_other_chief()
            if existing_chief:
                logger.warning(
                    "Chief conflict: peer %s also chief; local peer_id=%s. "
                    "Demoting (smaller peer_id wins).",
                    existing_chief,
                    self._mgr.local_peer.peer_id,
                )
                self._mgr.local_peer.roles = []
                return True
            await asyncio.sleep(0.5)

        return False

    def _find_other_chief(self) -> str | None:
        """Return the peer_id of another chief that outranks us, else None.

        Rules:
          - Same-machine chiefs (same api_host as local) are ignored so that a
            dev/test instance on another port cannot knock out the real one.
          - Tiebreaker: the node with the lexicographically smaller peer_id wins.
            We only demote if an existing chief has peer_id < ours.
        """
        local_id = self._mgr.local_peer.peer_id
        local_host = self._mgr.local_peer.api_host
        for peer in self._mgr.registry.list_all():
            if peer.peer_id == local_id:
                continue
            if "chief" not in getattr(peer, "roles", []):
                continue
            if peer.api_host and peer.api_host == local_host:
                continue
            if peer.peer_id < local_id:
                return peer.peer_id
        return None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._poll_loop())
        logger.info("FleetManager polling started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def refresh(self, *, force: bool = False) -> None:
        """Fetch /fleet/info from all peers (bypasses poll interval).

        Also prunes cache entries whose peer_id is no longer in the registry
        (e.g. the user removed a peer via the LAN Cowork settings page).

        ``force=True`` bypasses the soft-prune backoff so that user-triggered
        refresh hits every peer regardless of recent failure history. The
        background poll loop calls without ``force`` so unreachable peers
        don't burn the whole poll budget.
        """
        from .fleet_config import get_fleet_cfg, get_fleet_timings

        local_id = self._mgr.local_peer.peer_id
        peers = [p for p in self._mgr.registry.list_all() if p.peer_id != local_id]
        known_ids = {p.peer_id for p in peers}
        stale = [pid for pid in list(self._cache.keys()) if pid != local_id and pid not in known_ids]
        for pid in stale:
            self._cache.pop(pid, None)
            self._consecutive_failures.pop(pid, None)

        if not force:
            timings = get_fleet_timings(get_fleet_cfg(self._mgr))
            soft_cutoff = int(time.time()) - int(timings.get("soft_prune_sec", 3600))
            peers = [p for p in peers if self._is_polling_eligible(p, soft_cutoff)]

        await asyncio.gather(*[self._fetch_peer(p) for p in peers], return_exceptions=True)

    def _is_polling_eligible(self, peer, soft_cutoff: int) -> bool:
        """Return True if peer should be polled this tick.

        Peers we have never reached are always polled (so newly paired
        peers get a chance). Peers reached within the soft-prune window
        are polled. Peers last reached before ``soft_cutoff`` are skipped
        unless we've never recorded a successful reach (best-effort
        recovery).
        """
        last_reached = getattr(peer, "last_reached_at", None)
        if last_reached is None:
            return True
        return last_reached >= soft_cutoff

    def get_peers_snapshot(self) -> dict:
        """Return /fleet/peers response dict from cache.

        Intersect with the current registry so peers removed from the LAN
        Cowork side disappear from Fleet Admin immediately, without waiting
        for the next poll tick.
        """
        local_id = self._mgr.local_peer.peer_id
        known_ids = {p.peer_id for p in self._mgr.registry.list_all()}
        peers_list = []
        roles_index: dict[str, list] = {}

        for peer_id, entry in self._cache.items():
            if peer_id == local_id:
                continue
            if peer_id not in known_ids:
                continue
            info = entry.get("info") or {}
            # Hide peers whose most recent fetch was rejected with an auth
            # error and we've never obtained info from them — these are
            # unpaired/unauthorized peers whose host telemetry should not
            # leak into the Fleet overview (see /fleet/info strict auth).
            # Transient failures (network errors, 5xx) stay visible so paired
            # peers don't flicker in and out during outages.
            err = str(entry.get("last_error") or "")
            if not info and err.startswith("http_4"):
                continue
            roles = info.get("roles", []) if info else []
            for role in roles:
                roles_index.setdefault(role, [])
                if peer_id not in roles_index[role]:
                    roles_index[role].append(peer_id)

            registry_peer = self._mgr.registry.get(peer_id) if hasattr(self._mgr.registry, "get") else None
            peers_list.append({
                "peer_id": peer_id,
                "name": entry.get("name", ""),
                "roles": roles,
                "info": info,
                "last_fetched_at": entry.get("last_fetched_at"),
                "last_heartbeat_at": entry.get("last_heartbeat_at"),
                "reachable": entry.get("reachable", False),
                "last_error": entry.get("last_error"),
                "last_reached_at": getattr(registry_peer, "last_reached_at", None) if registry_peer else None,
                "last_attempted_at": getattr(registry_peer, "last_attempted_at", None) if registry_peer else None,
            })

        return {
            "responder_peer_id": local_id,
            "roles_index": roles_index,
            "peers": peers_list,
        }

    async def _poll_loop(self) -> None:
        from .fleet_config import get_fleet_cfg, get_fleet_timings
        while self._running:
            try:
                await self.refresh()
            except Exception:
                logger.exception("FleetManager poll error")
            fleet_cfg = get_fleet_cfg(self._mgr)
            interval = get_fleet_timings(fleet_cfg)["peers_poll_interval_sec"]
            await asyncio.sleep(interval)

    async def _fetch_peer(self, peer) -> None:
        import datetime

        import httpx

        from core.services_core.peer_registry_service import (
            update_peer_attempted,
            update_peer_reached,
        )

        from .fleet_peer_http import build_peer_headers

        path = "/ext/lan_cowork/fleet/info"
        headers = build_peer_headers(
            self._mgr,
            peer,
            requested_with="FleetManager",
            method="GET",
            full_path=path,
        )
        url = f"http://{peer.api_host}:{peer.api_port}{path}"
        now_ts = int(time.time())
        now_iso = datetime.datetime.now().astimezone().isoformat()
        existing = self._cache.get(peer.peer_id, {})

        last_error: str | None = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    try:
                        info = resp.json()
                        self._cache[peer.peer_id] = {
                            "name": peer.name,
                            "info": info,
                            "last_fetched_at": now_iso,
                            "last_heartbeat_at": existing.get("last_heartbeat_at"),
                            "reachable": True,
                            "last_error": None,
                        }
                        peer.last_reached_at = now_ts
                        peer.last_attempted_at = now_ts
                        self._consecutive_failures.pop(peer.peer_id, None)
                        try:
                            update_peer_reached(peer.peer_id, now_ts)
                        except Exception as exc:
                            logger.debug("update_peer_reached failed: %s", exc)
                        return
                    except Exception as json_exc:
                        # Common case: boss-mode decoy returns HTML with 200 —
                        # surface as a distinct error so we can tell the user
                        # to update the peer with the /fleet/info bypass rule.
                        last_error = f"non_json_200 ({json_exc})"
                else:
                    last_error = f"http_{resp.status_code}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        # Demote repeated failures from WARN to DEBUG to avoid log floods
        # when many peers are simply offline (DHCP rotation, sleeping nodes).
        fails = self._consecutive_failures.get(peer.peer_id, 0) + 1
        self._consecutive_failures[peer.peer_id] = fails
        if fails <= self._noise_threshold:
            logger.warning("FleetManager fetch %s failed: %s", peer.peer_id, last_error)
        else:
            logger.debug(
                "FleetManager fetch %s failed (x%d, suppressed): %s",
                peer.peer_id, fails, last_error,
            )
        self._cache[peer.peer_id] = {
            "name": peer.name,
            "info": existing.get("info"),
            # Record the attempt even on failure — otherwise last_fetched_at
            # stays null and it's impossible to tell if polling is running.
            "last_fetched_at": now_iso,
            "last_heartbeat_at": existing.get("last_heartbeat_at"),
            "reachable": False,
            "last_error": last_error,
        }
        peer.last_attempted_at = now_ts
        try:
            update_peer_attempted(peer.peer_id, now_ts)
        except Exception as exc:
            logger.debug("update_peer_attempted failed: %s", exc)

    def update_heartbeat_time(self, peer_id: str, iso_time: str) -> None:
        entry = self._cache.setdefault(peer_id, {})
        entry["last_heartbeat_at"] = iso_time
