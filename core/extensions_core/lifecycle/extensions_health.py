"""Unified extension health (runtime availability) API.

Extensions opt in by exporting a module-level ``get_health()`` callable from
their entry module. The callback must return a dict shaped like::

    {
        "available": bool,
        "checks": {"runtime_ok": bool, "hardware_ok": bool, ...},
        "reason": str,                 # human-readable English fallback
        "reason_i18n_key": str,        # optional, e.g. "hailo.reason.device_missing"
    }

``compute_health()`` wraps the call with a short timeout and a TTL cache so
the synchronous ``/api/extensions`` handler stays responsive even when a
provider performs hardware probes.

The probe is intentionally tolerant: missing callbacks, callbacks raising,
and timed-out callbacks all degrade to ``None`` rather than blocking the
response.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from core.extensions_core.extensions_defs import ExtensionManifest

logger = logging.getLogger(__name__)

# Tunables ---------------------------------------------------------------
HEALTH_TIMEOUT_S: float = 0.5      # 500 ms ceiling for a single probe
HEALTH_CACHE_TTL_S: float = 5.0    # serve cached result within this window
# Negative cache TTL: when a probe times out, the worker thread keeps running
# in the background (ThreadPoolExecutor cannot cancel a started task). We cache
# the timeout verdict longer than HEALTH_CACHE_TTL_S so we do not pile up new
# probes onto a still-hung previous one and exhaust the worker pool.
HEALTH_NEG_TTL_S: float = 30.0

# Shared executor — small pool; health probes are O(extensions) and not hot.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ext-health")
atexit.register(_executor.shutdown, wait=False)

# Cache entry shape: (timestamp, result, ttl). Storing the effective TTL on
# the entry lets timed-out entries linger longer than fresh results.
_cache: dict[str, tuple[float, dict[str, Any] | None, float]] = {}
_cache_lock = threading.Lock()
# Per-extension in-flight events guard against cache stampede: when N callers
# hit a cold cache simultaneously, only the first runs the probe; the rest
# wait on the event and read the result from _cache.
_inflight: dict[str, threading.Event] = {}
# Monotonic generation counter per extension name. Bumped on every cache
# invalidation; an in-flight probe captures the value before submitting and
# only writes back if the generation still matches. Protects against a slow
# probe writing stale data after the extension was unloaded/reloaded.
_generation: dict[str, int] = {}


def register_health_provider(manifest: ExtensionManifest, module: Any) -> None:
    """Discover ``get_health`` in *module* and attach it to *manifest*.

    Called by the extension loader after a module is successfully imported.
    Silent no-op if the module does not export a callable ``get_health``.
    """
    if module is None:
        return
    cb = getattr(module, "get_health", None)
    if cb is None or not callable(cb):
        return
    manifest.health_provider = cb
    logger.debug("%s: health provider registered", manifest.name)


def _call_with_timeout(cb: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
    """Run *cb* with the global timeout. Returns (result, timed_out)."""
    fut = _executor.submit(cb)
    try:
        return fut.result(timeout=HEALTH_TIMEOUT_S), False
    except FutureTimeout:
        # Note: fut.cancel() on a running task is a no-op in ThreadPoolExecutor;
        # the worker keeps running. The negative cache TTL prevents us from
        # resubmitting the same hung probe over and over.
        fut.cancel()
        return (
            {"available": False, "checks": {}, "reason": "health probe timed out", "reason_i18n_key": "ext.health.timeout"},
            True,
        )
    except Exception as exc:
        logger.debug("health probe raised: %s", exc, exc_info=True)
        return (
            {"available": False, "checks": {}, "reason": f"health probe error: {exc}", "reason_i18n_key": "ext.health.error"},
            False,
        )


def compute_health(manifest: ExtensionManifest) -> dict[str, Any] | None:
    """Return cached or freshly-probed health dict for *manifest*.

    Returns ``None`` when the extension does not expose a provider, so the
    response shape stays optional and unsurprising for the frontend.

    Cache stampede is avoided by a per-extension :class:`threading.Event`:
    only the first caller on a cold cache runs the probe; concurrent callers
    wait for it to publish the result.
    """
    cb = manifest.health_provider
    if cb is None:
        return None

    name = manifest.name
    now = time.monotonic()

    # Fast path: fresh cache hit.
    with _cache_lock:
        cached = _cache.get(name)
        if cached and (now - cached[0]) < cached[2]:
            return cached[1]
        # Cold or stale. If another caller is already probing, wait for them.
        ev = _inflight.get(name)
        if ev is None:
            ev = threading.Event()
            _inflight[name] = ev
            i_run_probe = True
        else:
            i_run_probe = False
        # Snapshot the generation so the writer can detect concurrent invalidation.
        gen_at_start = _generation.get(name, 0)

    if not i_run_probe:
        # Wait at most one full timeout window for the in-flight probe to
        # finish, then return whatever ended up in cache (or fall through to
        # running our own probe if the leader vanished without publishing).
        ev.wait(timeout=HEALTH_TIMEOUT_S + 0.1)
        with _cache_lock:
            cached = _cache.get(name)
            if cached:
                return cached[1]
        # Leader produced nothing — fall through and run ourselves.

    try:
        result, timed_out = _call_with_timeout(cb)

        # Light normalization so downstream code can rely on the shape.
        if isinstance(result, dict):
            result.setdefault("available", False)
            result.setdefault("checks", {})
            result.setdefault("reason", "")
            result.setdefault("reason_i18n_key", "")

        ttl = HEALTH_NEG_TTL_S if timed_out else HEALTH_CACHE_TTL_S
        with _cache_lock:
            # Discard the result if the cache was invalidated while we were
            # probing — the extension may have been unloaded or reloaded and
            # this stale verdict would mislead the next caller.
            if _generation.get(name, 0) == gen_at_start:
                _cache[name] = (now, result, ttl)
        return result
    finally:
        with _cache_lock:
            # Wake any concurrent waiters and clear the in-flight marker.
            _inflight.pop(name, None)
        ev.set()


def invalidate_health_cache(name: str | None = None) -> None:
    """Drop cached health entry for *name*, or all entries when None.

    Bumps the generation counter so any in-flight probe will not write its
    (now-stale) result back into the cache.
    """
    with _cache_lock:
        if name is None:
            _cache.clear()
            for n in list(_generation):
                _generation[n] = _generation[n] + 1
        else:
            _cache.pop(name, None)
            _generation[name] = _generation.get(name, 0) + 1
