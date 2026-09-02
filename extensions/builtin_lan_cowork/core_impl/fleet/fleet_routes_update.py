"""Update and restart-related fleet route registrations."""
from __future__ import annotations

from pathlib import Path

from .fleet_route_deps import FleetUpdateRouteDeps
from .fleet_route_guards import build_local_chief_getter, build_manager_getter
from .fleet_routes_restart import register_fleet_restart_routes
from .fleet_routes_static import register_fleet_static_routes
from .fleet_routes_update_dispatch import register_fleet_update_dispatch_routes
from .fleet_routes_update_helpers import gc_dispatches
from .fleet_routes_update_job import register_fleet_update_job_routes

_AUTH_PREFIX = "/ext/lan_cowork"


def register_fleet_update_routes(
    bp,
    get_manager,
    deps: FleetUpdateRouteDeps,
):
    auth_decorator = deps.auth_decorator
    session_ok = deps.session_ok

    runtime = {
        "fleet_cfg": deps.fleet_cfg,
        "repo_root": deps.repo_root,
        "update_status": deps.update_status,
        "run_update_job": deps.run_update_job,
        "load_last_job": deps.load_last_job,
        "save_last_job": deps.save_last_job,
        "load_dispatch_history": deps.load_dispatch_history,
        "save_dispatch_history": deps.save_dispatch_history,
        "dispatch_runner_cls": deps.dispatch_runner_cls,
        "restart_dispatch_runner_cls": deps.restart_dispatch_runner_cls,
        "check_update_allowed": deps.check_update_allowed,
        "check_restart_allowed": deps.check_restart_allowed,
        "active_jobs": {},
        "dispatches": {},
        "data_dir": str(Path(deps.repo_root) / "data"),
    }

    require_manager = build_manager_getter(get_manager)
    require_local_chief = build_local_chief_getter(
        require_manager,
        session_ok,
        message="chief only",
    )

    register_fleet_update_job_routes(
        bp,
        auth_decorator=auth_decorator,
        require_manager=require_manager,
        runtime=runtime,
        auth_prefix=_AUTH_PREFIX,
    )
    register_fleet_update_dispatch_routes(
        bp,
        require_local_chief=require_local_chief,
        runtime=runtime,
        gc_dispatches_fn=lambda: gc_dispatches(
            runtime["dispatches"],
            runtime["update_status"],
        ),
    )
    register_fleet_restart_routes(
        bp,
        auth_decorator=auth_decorator,
        require_manager=require_manager,
        require_local_chief=require_local_chief,
        runtime=runtime,
        gc_dispatches_fn=lambda: gc_dispatches(
            runtime["dispatches"],
            runtime["update_status"],
        ),
        auth_prefix=_AUTH_PREFIX,
    )
    register_fleet_static_routes(bp)
