"""Dependency containers for fleet route registration modules."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FleetCoreRouteDeps:
    auth_decorator: Callable[[Callable[..., Any]], Callable[..., Any]]
    session_ok: Callable[[], bool]
    fleet_cfg: Callable[[Any], dict]
    repo_root: str
    check_log_stream_allowed: Callable[..., tuple[bool, str]]
    build_peer_relay_url: Callable[..., str]


@dataclass(frozen=True)
class FleetAllowlistRouteDeps:
    auth_decorator: Callable[[Callable[..., Any]], Callable[..., Any]]
    session_ok: Callable[[], bool]
    allowlist_categories: dict[str, str]
    normalize_entries: Callable[[Any], list[str]]
    apply_allowlist_update: Callable[..., dict]
    proxy_allowlist_to_peer: Callable[..., Any]
    fetch_peer_allowlist_status: Callable[..., Any]


@dataclass(frozen=True)
class FleetUpdateRouteDeps:
    auth_decorator: Callable[[Callable[..., Any]], Callable[..., Any]]
    session_ok: Callable[[], bool]
    fleet_cfg: Callable[[Any], dict]
    repo_root: str
    update_status: Any
    run_update_job: Callable[..., Any]
    load_last_job: Callable[..., Any]
    save_last_job: Callable[..., Any]
    load_dispatch_history: Callable[..., Any]
    save_dispatch_history: Callable[..., Any]
    dispatch_runner_cls: type
    restart_dispatch_runner_cls: type
    check_update_allowed: Callable[..., Any]
    check_restart_allowed: Callable[..., Any]  # include_restart_allowlist=True version


@dataclass(frozen=True)
class FleetConsentRouteDeps:
    auth_decorator: Callable[[Callable[..., Any]], Callable[..., Any]]
    session_ok: Callable[[], bool]
    fleet_cfg: Callable[[Any], dict]
    consent_lock: Any
    consent_store: dict
    deny_cooldown: dict
    run_consent_janitor_once: Callable[..., Any]
    relay_consent_request: Callable[..., Any]
    relay_consent_status: Callable[..., Any]
    logger: Any
