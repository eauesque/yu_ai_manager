"""Shared in-flight request deduplication for read-only DB calls.

Extracted from ``routes/search.py`` so other ``core/<domain>_api/`` modules
can collapse identical concurrent cold reads without re-implementing the
plumbing. Use only on idempotent read-only paths; sharing a task across
write operations would change semantics.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from core.services_core.db_async import run_db_sync

T = TypeVar("T")

_INFLIGHT_LOCK = asyncio.Lock()
_INFLIGHT_GETS: dict[str, asyncio.Task] = {}
# Strong refs for cleanup tasks. asyncio.create_task only weakly holds tasks,
# so a fire-and-forget task scheduled from a done_callback may be GC'd before
# it runs — leaving _INFLIGHT_GETS entries dangling. Pin them here and
# discard on completion.
_INFLIGHT_CLEANUP_TASKS: set[asyncio.Task] = set()


def _inflight_key(namespace: str, key_obj: Any) -> str:
    raw = namespace + "\0" + json.dumps(key_obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


def _schedule_inflight_clear(key: str, done: asyncio.Task) -> None:
    try:
        cleanup = asyncio.create_task(_clear_inflight_get(key, done))
    except RuntimeError:
        # No running loop (e.g. during shutdown) — clean up synchronously.
        _INFLIGHT_GETS.pop(key, None)
        return
    _INFLIGHT_CLEANUP_TASKS.add(cleanup)
    cleanup.add_done_callback(_INFLIGHT_CLEANUP_TASKS.discard)


async def _clear_inflight_get(key: str, task: asyncio.Task) -> None:
    async with _INFLIGHT_LOCK:
        if _INFLIGHT_GETS.get(key) is task:
            del _INFLIGHT_GETS[key]


async def dedupe_db_get(namespace: str, key_obj: Any, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``run_db_sync(fn, *args, **kwargs)`` but share concurrent identical calls.

    ``namespace`` (e.g. ``"favorites-check"``) and ``key_obj`` (any
    JSON-serializable representation of the inputs) together identify the
    request. Concurrent callers with the same hash await the in-flight task
    instead of issuing a duplicate DB call.

    Non-owners receive a deepcopy so they can mutate the result without
    affecting other waiters. Owners receive the original.
    """
    key = _inflight_key(namespace, key_obj)
    async with _INFLIGHT_LOCK:
        task = _INFLIGHT_GETS.get(key)
        if task is None:
            task = asyncio.create_task(run_db_sync(fn, *args, **kwargs))
            _INFLIGHT_GETS[key] = task
            task.add_done_callback(
                lambda done, done_key=key: _schedule_inflight_clear(done_key, done)
            )
            owner = True
        else:
            owner = False
    result = await asyncio.shield(task)
    return copy.deepcopy(result) if not owner else result


async def dedupe_awaitable(namespace: str, key_obj: Any, factory: Callable[[], Awaitable[T]]) -> T:
    """Lower-level: dedupe an arbitrary awaitable (not necessarily DB).

    ``factory`` is called only when no task is already in flight for the key.
    Useful when the underlying call already wraps its own dispatcher (e.g.
    ``run_in_heavy_io``).
    """
    key = _inflight_key(namespace, key_obj)
    async with _INFLIGHT_LOCK:
        task = _INFLIGHT_GETS.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            _INFLIGHT_GETS[key] = task
            task.add_done_callback(
                lambda done, done_key=key: _schedule_inflight_clear(done_key, done)
            )
            owner = True
        else:
            owner = False
    result = await asyncio.shield(task)
    return copy.deepcopy(result) if not owner else result
