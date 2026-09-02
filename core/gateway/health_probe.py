from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_PROBE_PATHS = {
    "ollama":      "/api/tags",
    "sd_webui":    "/sdapi/v1/sd-models",
    "comfyui":     "/system_stats",
    "agentmemory": "/agentmemory/livez",
    "gradio":      "/",
    "headroom":    "/livez",
}


@dataclass(frozen=True)
class BackendEntry:
    type: str
    base_url: str


class BackendState(StrEnum):
    UNKNOWN = "unknown"
    RUNNING = "running"
    STOPPED = "stopped"


class HealthProbe:
    def __init__(
        self,
        backends: dict[str, BackendEntry],
        db_path: Path,
        interval: float = 10.0,
        probe_timeout: float = 3.0,
    ) -> None:
        self._backends = backends
        self._db_path = db_path
        self._interval = interval
        self._probe_timeout = probe_timeout
        self._states: dict[str, BackendState] = {k: BackendState.UNKNOWN for k in backends}
        self._task: asyncio.Task | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    def get_state(self, backend_id: str) -> BackendState:
        return self._states.get(backend_id, BackendState.UNKNOWN)

    def get_all_states(self) -> dict[str, BackendState]:
        return dict(self._states)

    async def update_backends(self, new: dict[str, BackendEntry]) -> None:
        async with self._lock:
            old = self._backends
            for bid, entry in new.items():
                if bid not in old or old[bid] != entry:
                    self._states[bid] = BackendState.UNKNOWN
            for bid in list(self._states.keys()):
                if bid not in new:
                    del self._states[bid]
            self._backends = new

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._event_loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._loop(), name="gateway-health-probe")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        while True:
            await self._probe_once()
            await asyncio.sleep(self._interval)

    async def _probe_once(self) -> None:
        async with self._lock:
            snapshot = dict(self._backends)
        to_record: list[tuple[str, BackendState, BackendState]] = []
        async with httpx.AsyncClient(timeout=self._probe_timeout) as client:
            for bid, entry in snapshot.items():
                if "127.0.0.1" not in entry.base_url and "localhost" not in entry.base_url:
                    logger.warning("[gateway:health] %s base_url %r is not loopback", bid, entry.base_url)
                url = entry.base_url.rstrip("/") + _PROBE_PATHS.get(entry.type, "/")
                try:
                    resp = await client.get(url)
                    new_state = BackendState.RUNNING if resp.status_code == 200 else BackendState.STOPPED
                except Exception:
                    new_state = BackendState.STOPPED
                async with self._lock:
                    current = self._backends.get(bid)
                    if current is None or current != snapshot[bid]:
                        continue
                    prev = self._states.get(bid, BackendState.UNKNOWN)
                    if new_state != prev:
                        self._states[bid] = new_state
                        logger.info("[gateway:health] %s: %s -> %s", bid, prev, new_state)
                        to_record.append((bid, prev, new_state))
        for bid, prev, new_state in to_record:
            # Offload the SQLCipher write (connect + PBKDF2 ~250-500 ms on Pi)
            # to a worker thread so the probe loop doesn't stall the event loop.
            await asyncio.to_thread(self._record, bid, prev, new_state)

    def _record(self, bid: str, prev: BackendState, new: BackendState) -> None:
        if not self._db_path.exists():
            return
        try:
            from core.gateway.status_log import record_transition
            record_transition(self._db_path, bid, str(prev), str(new), datetime.now(UTC))
        except Exception as exc:
            logger.warning("[gateway:health] transition record failed: %s", exc)
