"""Shared backend registry for the gateway.

All modules MUST use this API. Direct mutation of _backends in gateway_backends.py
is forbidden after this migration.

Thread safety: asyncio.Lock serialises mutations. get_*/list_* return deep copies.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

FALLBACK_URLS: dict[str, str] = {
    "comfyui": "http://127.0.0.1:8188",
    "sd_webui": "http://127.0.0.1:7860",
    "gradio":   "http://127.0.0.1:7861",
}

_DEFAULT_COLORS = {"comfyui": "#4a9eff", "sd_webui": "#ff7a4a", "gradio": "#f97316"}

# Internal mutable state
_lock = asyncio.Lock()
_backends: dict[str, dict[str, Any]] = {}
_defaults: dict[str, str | None] = {
    "default_comfy_backend_id": None,
    "default_sd_backend_id": None,
}
_groups: dict[str, dict[str, Any]] = {}
_invalidation_callbacks: list[Callable[[str, str], None]] = []
_probe: Any = None


@dataclass
class ResolveResult:
    base_url: str
    resolved_backend_id: str
    source: str
    error_kind: str | None


# Read API - return deep copies


def get_backend(backend_id: str) -> dict[str, Any] | None:
    e = _backends.get(backend_id)
    return copy.deepcopy(e) if e else None


def list_backends() -> list[dict[str, Any]]:
    result = []
    for bid, e in _backends.items():
        item = copy.deepcopy(e)
        item["id"] = bid
        result.append(item)
    return result


def get_defaults() -> dict[str, str | None]:
    return copy.deepcopy(_defaults)


def get_group(group_id: str) -> dict[str, Any] | None:
    e = _groups.get(group_id)
    return copy.deepcopy(e) if e else None


def list_groups() -> list[dict[str, Any]]:
    result = []
    for gid, e in _groups.items():
        item = copy.deepcopy(e)
        item["id"] = gid
        result.append(item)
    return result


def resolve_backend_by_name(bridge_type: str, name: str) -> ResolveResult:
    """Resolve backend by display name. Returns error_kind='not_found' if no match."""
    for bid, e in _backends.items():
        if e.get("type") == bridge_type and e.get("name") == name:
            return ResolveResult(e["base_url"], bid, "name", None)
    return ResolveResult("", "", "name", "not_found")


def resolve_backend(bridge_type: str, backend_id: str | None) -> ResolveResult:
    """Resolve routing. error_kind only set for explicit backend_id failures."""
    fallback = FALLBACK_URLS.get(bridge_type, "http://127.0.0.1:8188")

    if backend_id:
        e = _backends.get(backend_id)
        if e is None:
            return ResolveResult(fallback, "__fallback__", "specified", "not_found")
        if e.get("type") != bridge_type:
            return ResolveResult(fallback, "__fallback__", "specified", "type_mismatch")
        return ResolveResult(e["base_url"], backend_id, "specified", None)

    default_key = "default_comfy_backend_id" if bridge_type == "comfyui" else "default_sd_backend_id"
    default_id = _defaults.get(default_key)
    if default_id:
        e = _backends.get(default_id)
        if e and e.get("type") == bridge_type:
            return ResolveResult(e["base_url"], default_id, "default", None)
        logger.warning("Default backend %s for %s invalid; using fallback", default_id, bridge_type)

    return ResolveResult(fallback, "__fallback__", "fallback", None)


# Mutation API


async def mutate_and_save(fn: Callable[[], Any]) -> Any:
    """Serialised mutation with rollback on save failure.

    Lock -> rollback snapshot -> fn() -> save config -> release lock
    -> await update_backends(new_map).
    On save failure: rollback in-memory, re-raise.
    On probe update failure: log WARNING; probe recovers on next cycle (no rollback).
    """
    async with _lock:
        old_b = copy.deepcopy(_backends)
        old_d = copy.deepcopy(_defaults)
        old_g = copy.deepcopy(_groups)

        result = fn()
        new_entries = _build_probe_entries()

        try:
            _save_registry_to_config()
        except Exception:
            _backends.clear()
            _backends.update(old_b)
            _defaults.clear()
            _defaults.update(old_d)
            _groups.clear()
            _groups.update(old_g)
            raise

    if _probe is not None:
        try:
            await _probe.update_backends(new_entries)
        except Exception as exc:
            logger.warning(
                "HealthProbe update failed after mutation: %s",
                exc,
                exc_info=True,
            )
            # Probe will recover on next probe cycle.

    return result


def _save_registry_to_config() -> None:
    try:
        from core.configuration.json_rw import load_config_json, save_config_json

        cfg = load_config_json()
        gateway_cfg = cfg.setdefault("gateway", {})
        gateway_cfg["backends"] = {
            bid: {
                key: copy.deepcopy(value)
                for key, value in backend.items()
                if key != "id"
            }
            for bid, backend in _backends.items()
        }
        gateway_cfg["defaults"] = copy.deepcopy(_defaults)
        gateway_cfg["groups"] = copy.deepcopy(_groups)
        save_config_json(cfg)
    except Exception as exc:
        logger.warning(
            "[gateway:backend_registry] save to config failed: %s",
            exc,
            exc_info=True,
        )
        raise


def _build_probe_entries() -> dict[str, Any]:
    from core.gateway.health_probe import BackendEntry

    return {
        bid: BackendEntry(type=e["type"], base_url=e["base_url"])
        for bid, e in _backends.items()
    }


def set_probe(probe: Any) -> None:
    global _probe
    _probe = probe


def get_probe() -> Any:
    """The health probe, or None before startup registers one.

    Exists so core-side callers do not have to reach into routes for it --
    core must not depend on routes (tests/basic/test_python_structure_guards).
    """
    return _probe


# Invalidation


def register_invalidation_callback(callback: Callable[[str, str], None]) -> None:
    """callback(backend_id, reason): reason = 'deleted'|'base_url_changed'|'type_changed'"""
    _invalidation_callbacks.append(callback)


def fire_invalidation(backend_id: str, reason: str) -> None:
    for cb in _invalidation_callbacks:
        try:
            cb(backend_id, reason)
        except Exception as exc:
            logger.warning("Invalidation callback error: %s", exc)


# Helpers


def apply_backend_defaults(entry: dict[str, Any]) -> dict[str, Any]:
    # Mutates entry in-place and returns it for chaining convenience.
    if not entry.get("name"):
        parsed = urlparse(entry.get("base_url", ""))
        netloc = parsed.netloc or parsed.path
        entry["name"] = f"{entry.get('type', '')}:{netloc}"
    if not entry.get("color"):
        entry["color"] = _DEFAULT_COLORS.get(entry.get("type", ""), "#888888")
    return entry


def load_state(
    backends: dict[str, dict[str, Any]],
    defaults: dict[str, str | None],
    groups: dict[str, dict[str, Any]],
) -> None:
    """Called once at startup from gateway_backends._load_from_config()."""
    _backends.clear()
    _backends.update(copy.deepcopy(backends))
    _defaults.clear()
    _defaults.update(copy.deepcopy(defaults))
    _groups.clear()
    _groups.update(copy.deepcopy(groups))
