"""Fleet admin routes — registered on the lan_cowork Blueprint."""
from __future__ import annotations

import logging
from pathlib import Path

from quart import Blueprint

from .fleet_consent_store import (
    _consent_lock,
    _consent_store,
    _deny_cooldown,
)
from .fleet_consent_store import (
    consume_consent_token as _consume_consent_token,
)
from .fleet_consent_store import (
    run_consent_janitor_once as _run_consent_janitor_once,
)
from .fleet_dispatch import DispatchRunner, RestartDispatchRunner
from .fleet_peer_http import (
    fetch_peer_allowlist_status,
    proxy_allowlist_to_peer,
    relay_consent_request,
    relay_consent_status,
)
from .fleet_route_deps import (
    FleetAllowlistRouteDeps,
    FleetConsentRouteDeps,
    FleetCoreRouteDeps,
    FleetUpdateRouteDeps,
)
from .fleet_route_helpers import (
    ALLOWLIST_CATEGORIES as _ALLOWLIST_CATEGORIES,
)
from .fleet_route_helpers import (
    apply_allowlist_update as _apply_allowlist_update,
)
from .fleet_route_helpers import (
    build_peer_relay_url,
    check_log_stream_allowed,
)
from .fleet_route_helpers import (
    get_fleet_cfg as _fleet_cfg,
)
from .fleet_route_helpers import (
    normalize_entries as _normalize_entries,
)
from .fleet_route_security import (
    check_update_allowed,
    make_session_checker,
)
from .fleet_routes_allowlists import register_fleet_allowlist_routes
from .fleet_routes_consent import register_fleet_consent_routes
from .fleet_routes_core import register_fleet_core_routes
from .fleet_routes_update import register_fleet_update_routes
from .updater import (
    UpdateStatus,
    load_dispatch_history,
    load_last_job,
    run_update_job,
    save_dispatch_history,
    save_last_job,
)

logger = logging.getLogger(__name__)

# Repo root relative to this file: fleet/ -> core_impl/ -> lan-cowork/ -> extensions/ -> repo root
_REPO_ROOT = str(Path(__file__).resolve().parents[4])


def register_fleet_routes(bp: Blueprint, get_manager, session_guard=None) -> None:
    """Attach /ext/lan_cowork/fleet/* routes to bp."""
    from ..peer_auth import require_peer_auth

    _auth = require_peer_auth(get_manager)
    _session_ok = make_session_checker(session_guard)
    _fleet_cfg_getter = lambda mgr: _fleet_cfg(mgr)

    register_fleet_core_routes(
        bp,
        get_manager,
        FleetCoreRouteDeps(
            auth_decorator=_auth,
            session_ok=_session_ok,
            fleet_cfg=_fleet_cfg_getter,
            repo_root=_REPO_ROOT,
            check_log_stream_allowed=check_log_stream_allowed,
            build_peer_relay_url=build_peer_relay_url,
        ),
    )

    register_fleet_allowlist_routes(
        bp,
        get_manager,
        FleetAllowlistRouteDeps(
            auth_decorator=_auth,
            session_ok=_session_ok,
            allowlist_categories=_ALLOWLIST_CATEGORIES,
            normalize_entries=_normalize_entries,
            apply_allowlist_update=_apply_allowlist_update,
            proxy_allowlist_to_peer=proxy_allowlist_to_peer,
            fetch_peer_allowlist_status=fetch_peer_allowlist_status,
        ),
    )
    register_fleet_update_routes(
        bp,
        get_manager,
        FleetUpdateRouteDeps(
            auth_decorator=_auth,
            session_ok=_session_ok,
            fleet_cfg=_fleet_cfg_getter,
            repo_root=_REPO_ROOT,
            update_status=UpdateStatus,
            run_update_job=lambda **kwargs: run_update_job(**kwargs),
            load_last_job=load_last_job,
            save_last_job=save_last_job,
            load_dispatch_history=load_dispatch_history,
            save_dispatch_history=save_dispatch_history,
            dispatch_runner_cls=DispatchRunner,
            restart_dispatch_runner_cls=RestartDispatchRunner,
            check_update_allowed=lambda mgr, requester_peer_id, *, allow_consent=True: check_update_allowed(
                mgr,
                requester_peer_id,
                fleet_cfg_getter=_fleet_cfg_getter,
                consume_consent_token=_consume_consent_token,
                allow_consent=allow_consent,
                include_restart_allowlist=False,  # update does not check allow_restart_from
            ),
            check_restart_allowed=lambda mgr, requester_peer_id, *, allow_consent=True: check_update_allowed(
                mgr,
                requester_peer_id,
                fleet_cfg_getter=_fleet_cfg_getter,
                consume_consent_token=_consume_consent_token,
                allow_consent=allow_consent,
                include_restart_allowlist=True,  # restart also checks allow_restart_from
            ),
        ),
    )
    register_fleet_consent_routes(
        bp,
        get_manager,
        FleetConsentRouteDeps(
            auth_decorator=_auth,
            session_ok=_session_ok,
            fleet_cfg=_fleet_cfg_getter,
            consent_lock=_consent_lock,
            consent_store=_consent_store,
            deny_cooldown=_deny_cooldown,
            run_consent_janitor_once=_run_consent_janitor_once,
            relay_consent_request=relay_consent_request,
            relay_consent_status=relay_consent_status,
            logger=logger,
        ),
    )
