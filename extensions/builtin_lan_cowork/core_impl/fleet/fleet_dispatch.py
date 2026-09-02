"""Dispatch runners for fleet update and restart operations."""
from __future__ import annotations

import asyncio
import datetime

from .fleet_peer_http import (
    fetch_peer_uptime,
    get_peer_or_raise,
    poll_peer_update_job,
    post_peer_restart,
    post_peer_update,
)
from .updater import UpdateStatus


class RestartDispatchRunner:
    """Chief-side runner for parallel peer restarts."""

    def __init__(self, mgr, dispatch_id: str, peer_ids: list[str]) -> None:
        if mgr.local_peer.peer_id in peer_ids:
            raise ValueError("cannot_dispatch_self")
        self._mgr = mgr
        self.dispatch_id = dispatch_id
        self._peer_ids = list(peer_ids)
        self._started_at = datetime.datetime.now().astimezone().isoformat()
        self._finished_at: str | None = None
        self._status = UpdateStatus.PENDING
        self._peers: list[dict] = [
            {"peer_id": pid, "status": UpdateStatus.PENDING, "current_step": None, "error": None, "pre_uptime": None}
            for pid in self._peer_ids
        ]

    def get_status(self) -> dict:
        return {
            "dispatch_id": self.dispatch_id,
            "kind": "restart",
            "status": self._status,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "peers": list(self._peers),
        }

    async def run(self) -> None:
        self._status = UpdateStatus.RUNNING
        await asyncio.gather(*(self._restart_one(entry) for entry in self._peers), return_exceptions=True)
        any_failed = any(p["status"] == UpdateStatus.FAILED for p in self._peers)
        self._status = UpdateStatus.FAILED if any_failed else UpdateStatus.SUCCESS
        self._finished_at = datetime.datetime.now().astimezone().isoformat()

    async def _fetch_uptime(self, peer, _headers: dict | None = None) -> int | None:
        return await fetch_peer_uptime(self._mgr, peer)

    async def _post_restart(self, peer) -> tuple[bool, str | None]:
        return await post_peer_restart(self._mgr, peer)

    async def _restart_one(self, entry: dict) -> None:
        pid = entry["peer_id"]
        try:
            peer = get_peer_or_raise(self._mgr, pid)
        except ValueError:
            entry["status"] = UpdateStatus.FAILED
            entry["error"] = "peer_not_found"
            return

        pre_uptime = await self._fetch_uptime(peer, None)
        if pre_uptime is None:
            entry["status"] = UpdateStatus.FAILED
            entry["error"] = "pre_uptime_unavailable"
            return
        entry["pre_uptime"] = pre_uptime
        entry["status"] = UpdateStatus.RUNNING
        entry["current_step"] = "restart_signal"

        ok, error = await self._post_restart(peer)
        if not ok:
            entry["status"] = UpdateStatus.FAILED
            entry["error"] = error
            return

        entry["current_step"] = "awaiting_restart"
        deadline = asyncio.get_event_loop().time() + 60.0
        saw_down = False
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(3)
            up = await self._fetch_uptime(peer, None)
            if up is None:
                saw_down = True
                continue
            if saw_down and up < pre_uptime:
                entry["status"] = UpdateStatus.SUCCESS
                entry["current_step"] = "online"
                entry["post_uptime"] = up
                return
        entry["status"] = UpdateStatus.FAILED
        entry["error"] = "restart_timeout"


class DispatchRunner:
    """Chief-side runner for sequential peer update dispatch."""

    def __init__(self, mgr, dispatch_id: str, peer_ids: list[str], source: str, branch: str, consent_tokens: dict | None = None) -> None:
        if mgr.local_peer.peer_id in peer_ids:
            raise ValueError("cannot_dispatch_self")
        self._mgr = mgr
        self.dispatch_id = dispatch_id
        self._peer_ids = list(peer_ids)
        self._source = source
        self._branch = branch
        self._consent_tokens: dict[str, str] = dict(consent_tokens or {})
        self._started_at = datetime.datetime.now().astimezone().isoformat()
        self._finished_at: str | None = None
        self._status = UpdateStatus.PENDING
        self._peers: list[dict] = [
            {"peer_id": pid, "job_id": None, "status": UpdateStatus.PENDING, "current_step": None, "error": None}
            for pid in self._peer_ids
        ]

    def get_status(self) -> dict:
        return {
            "dispatch_id": self.dispatch_id,
            "status": self._status,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "source": self._source,
            "branch": self._branch,
            "peers": list(self._peers),
        }

    async def run(self) -> None:
        from .fleet_config import get_fleet_cfg, get_fleet_timings

        self._status = UpdateStatus.RUNNING
        for peer_entry in self._peers:
            pid = peer_entry["peer_id"]
            try:
                job = await self._post_update_to_peer(pid, self._source, self._branch)
                job_id = job.get("job_id")
                if not job_id:
                    peer_entry["status"] = UpdateStatus.FAILED
                    peer_entry["error"] = job.get("error") or "no_job_id"
                    continue
                peer_entry["job_id"] = job_id
                peer_entry["status"] = UpdateStatus.RUNNING

                fleet_cfg = get_fleet_cfg(self._mgr)
                timings = get_fleet_timings(fleet_cfg)
                timeout = timings["update_job_timeout_sec"] + timings["postcheck_timeout_sec"]

                result = await self._poll_peer_job(pid, job_id, timeout)
                peer_entry["status"] = result.get("status", UpdateStatus.FAILED)
                steps = result.get("steps", [])
                if steps:
                    peer_entry["current_step"] = steps[-1].get("name")
                peer_entry["error"] = result.get("error")
            except TimeoutError:
                peer_entry["status"] = UpdateStatus.FAILED
                peer_entry["error"] = "timeout"
            except Exception as exc:
                peer_entry["status"] = UpdateStatus.FAILED
                peer_entry["error"] = str(exc)

        any_failed = any(p["status"] == UpdateStatus.FAILED for p in self._peers)
        self._status = UpdateStatus.FAILED if any_failed else UpdateStatus.SUCCESS
        self._finished_at = datetime.datetime.now().astimezone().isoformat()

    async def _post_update_to_peer(self, peer_id: str, source: str, branch: str) -> dict:
        peer = get_peer_or_raise(self._mgr, peer_id)
        return await post_peer_update(
            self._mgr,
            peer,
            source=source,
            branch=branch,
            consent_token=self._consent_tokens.get(peer_id, ""),
        )

    async def _poll_peer_job(self, peer_id: str, job_id: str, timeout: float) -> dict:
        peer = get_peer_or_raise(self._mgr, peer_id)
        return await poll_peer_update_job(self._mgr, peer, job_id=job_id, timeout=timeout)
