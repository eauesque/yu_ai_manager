from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_PORTS = (7860, 8188, 11434)
_PROBE_PATHS_ORDERED = [
    ("sd_webui", "/sdapi/v1/sd-models"),
    ("comfyui", "/system_stats"),
    ("ollama", "/api/tags"),
]
_EXCLUDED_PORTS: frozenset[int] = frozenset(
    {22, 25, 53, 80, 443, 5432, 3306, 6379, 27017}
) | frozenset(range(5000, 5100))

SCAN_BATCH_SIZE = 50
SCAN_TIMEOUT = 1.5
JOB_TTL = 300
CANCELLED_TTL = 30


def _build_port_list(params: dict[str, Any]) -> list[int]:
    ports: set[int] = set()
    if params.get("include_defaults", True):
        ports.update(_DEFAULT_PORTS)
    if params.get("full_scan"):
        ports.update(range(1, 65536))
    elif r := params.get("range"):
        ports.update(range(r["min"], r["max"] + 1))
    if own := params.get("_own_port"):
        ports.discard(own)
    return sorted(p for p in ports if p not in _EXCLUDED_PORTS)


@dataclass
class ScanJob:
    scan_id: str
    task: asyncio.Task | None = None
    _progress: dict[str, Any] | None = None
    _stable: list[dict[str, Any]] = field(default_factory=list)
    state: str = "running"
    done_at: float | None = None
    _waiters: list[asyncio.Queue] = field(default_factory=list)

    def add_event(self, event: dict[str, Any]) -> None:
        if event["type"] == "progress":
            self._progress = event
        else:
            self._stable.append(event)
            if event["type"] in ("done", "cancelled"):
                self.state = event["type"]
                self.done_at = time.monotonic()
        for q in list(self._waiters):
            q.put_nowait(event)

    def get_buffered(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if self._progress:
            result.append(self._progress)
        result.extend(self._stable)
        return result

    def subscribe(self, q: asyncio.Queue) -> None:
        self._waiters.append(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with contextlib.suppress(ValueError):
            self._waiters.remove(q)


class ScanRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}
        self._active_id: str | None = None
        self._lock = asyncio.Lock()

    async def start_scan(self, params: dict[str, Any]) -> ScanJob:
        async with self._lock:
            if (
                self._active_id
                and self._active_id in self._jobs
                and self._jobs[self._active_id].state == "running"
            ):
                raise ValueError("conflict")
            scan_id = str(uuid.uuid4())
            job = ScanJob(scan_id=scan_id)
            self._jobs[scan_id] = job
            self._active_id = scan_id
        probe_fn = params.pop("_probe_fn", _default_probe)
        job.task = asyncio.create_task(
            _run_scan(job, params, probe_fn),
            name=f"gw-scan-{scan_id[:8]}",
        )
        return job

    async def cancel_scan(self, scan_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(scan_id)
            if job is None or job.state != "running":
                return False
            if job.task:
                job.task.cancel()
            if self._active_id == scan_id:
                self._active_id = None
        job.add_event({"type": "cancelled"})
        return True

    def get_job(self, scan_id: str) -> ScanJob | None:
        job = self._jobs.get(scan_id)
        if job is None:
            return None
        if job.state != "running" and job.done_at:
            ttl = CANCELLED_TTL if job.state == "cancelled" else JOB_TTL
            if time.monotonic() - job.done_at > ttl:
                self._jobs.pop(scan_id, None)
                return None
        return job


async def _run_scan(
    job: ScanJob,
    params: dict[str, Any],
    probe_fn: Callable[[int], Coroutine[Any, Any, tuple[str, str] | None]],
) -> None:
    found = registered = 0
    try:
        ports = _build_port_list(params)
        total = len(ports)
        scanned = 0
        register_cb = params.get("_register_cb")

        for i in range(0, total, SCAN_BATCH_SIZE):
            batch = ports[i : i + SCAN_BATCH_SIZE]
            results = await asyncio.gather(*[probe_fn(p) for p in batch], return_exceptions=True)
            for port, result in zip(batch, results, strict=False):
                scanned += 1
                if isinstance(result, BaseException) or result is None:
                    continue
                btype, base_url = result
                entry: dict[str, Any] = {"type": btype, "port": port, "base_url": base_url}
                if params.get("auto_register") and register_cb:
                    ok, already = await register_cb(btype, port, base_url)
                    entry["registered"] = ok
                    if already:
                        entry["already_existed"] = True
                    elif ok:
                        registered += 1
                else:
                    entry["registered"] = False
                job.add_event({"type": "found", "entry": entry})
                found += 1
            job.add_event({"type": "progress", "scanned": scanned, "total": total})
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.exception("[scan] unexpected error: %s", exc)
        job.add_event({"type": "error", "port": 0, "reason": "probe_error"})
        # Ensure job reaches terminal state so next scan is not blocked with 409.
        job.add_event({"type": "done", "found": found, "registered": registered})
    else:
        job.add_event({"type": "done", "found": found, "registered": registered})


async def _default_probe(port: int) -> tuple[str, str] | None:
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as client:
        tasks = [
            asyncio.create_task(client.get(f"{base}{path}"), name=f"{bt}-{port}")
            for bt, path in _PROBE_PATHS_ORDERED
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = [
        bt
        for (bt, _), r in zip(_PROBE_PATHS_ORDERED, results, strict=False)
        if not isinstance(r, BaseException) and r.status_code == 200
    ]
    if not successes:
        return None
    if len(successes) > 1:
        logger.debug(
            "[scan] port %d matched multiple types: %s -> using %s",
            port,
            successes,
            successes[0],
        )
    return successes[0], base
