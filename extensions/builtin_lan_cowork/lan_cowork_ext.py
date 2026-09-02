"""builtin-lan-cowork Extension entrypoint."""
from __future__ import annotations

import asyncio
import ipaddress
import logging

from quart import Blueprint, redirect, render_template, session, url_for

from .manager import CoworkManager

logger = logging.getLogger(__name__)

_manager: CoworkManager | None = None
_init_task: asyncio.Task | None = None


def _get_manager() -> CoworkManager | None:
    return _manager


def is_loopback_listener(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except (TypeError, ValueError):
        return False


def get_blueprint() -> Blueprint:
    bp = Blueprint("lan_cowork", __name__, template_folder="templates")

    from .routes.gen_api import register_routes as register_gen_routes
    from .routes.infer_api import register_routes as register_infer_routes
    from .routes.local_import_api import register_routes as register_local_import
    from .routes.negotiate_api import register_routes as register_negotiate_routes
    from .routes.peer_api import register_routes
    from .routes.remote_import_api import register_routes as register_remote_import
    from .routes.sync_api import register_routes as register_sync_routes

    def _session_guard() -> bool:
        from quart import current_app
        if not current_app.config.get("PIN_AUTH"):
            return True
        return bool(session.get("pin_ok"))

    register_sync_routes(bp, _get_manager)
    register_gen_routes(bp, _get_manager)
    register_infer_routes(bp, _get_manager)
    register_negotiate_routes(bp, _get_manager)
    register_remote_import(bp, _get_manager)
    register_local_import(bp, _get_manager, session_guard=_session_guard)

    def _get_pairing_service():
        mgr = _get_manager()
        return mgr.pairing_service if mgr is not None else None

    def _get_token_store():
        mgr = _get_manager()
        return mgr.token_store if mgr is not None else None

    register_routes(bp, _get_manager, session_guard=_session_guard)

    from .core_impl.fleet.fleet_routes import register_fleet_routes
    from .routes.client_api import register_routes as reg_client
    from .routes.pair_api import register_routes as reg_pair
    from .routes.peer_admin_api import register_routes as reg_peer_admin
    from .routes.settings_api import register_routes as reg_settings

    reg_pair(bp, pairing_service=_get_pairing_service, session_guard=_session_guard, get_manager=_get_manager)
    reg_peer_admin(bp, token_store=_get_token_store, session_guard=_session_guard, get_manager=_get_manager)
    reg_client(bp, get_manager=_get_manager, session_guard=_session_guard)
    reg_settings(bp, get_manager=_get_manager, session_guard=_session_guard)
    register_fleet_routes(bp, _get_manager, session_guard=_session_guard)

    @bp.route("/peers")
    async def lan_cowork_peers():
        if not _session_guard():
            return redirect(f"/_pin?next={url_for('lan_cowork.lan_cowork_peers')}")
        return await render_template("lan_cowork_peers.html")

    @bp.record_once
    def _on_register(state):
        global _manager
        app = state.app
        ext_cfg = app.config.get("EXTENSIONS", {}).get("builtin-lan-cowork", {})
        if not ext_cfg.get("enabled", False):
            try:
                from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
                # Default to True when config.json has no entry — matches
                # extension.json's declared `config.enabled: true` and the
                # loader's behavior in extensions_loader_manifest.py.
                if not get_extension_config_value("builtin-lan-cowork", "enabled", True):
                    logger.info("LAN Cowork disabled by config")
                    return
                import json

                from core.extensions_core.lifecycle.extensions_admin import _config_path
                try:
                    raw = json.loads(_config_path().read_text(encoding="utf-8"))
                    ext_cfg = raw.get("extensions", {}).get("builtin-lan-cowork", {})
                except Exception as exc:
                    logger.warning("Failed to read %s for ext_cfg: %s", _config_path(), exc)
                    ext_cfg = {"enabled": True}
            except Exception:
                logger.info("LAN Cowork disabled by config")
                return

        async def _start_cowork():
            global _manager
            try:
                mgr = CoworkManager(
                    ext_cfg,
                    loopback_listener=is_loopback_listener(app.config.get("HOST", "")),
                )
                mgr.local_peer.api_port = app.config.get("PORT", 5000)
                # Publish the manager BEFORE awaiting start() so routes that
                # only need a handle (no started state) see it; start() may
                # take many seconds when peers are offline.
                _manager = mgr
                await mgr.start()
            except Exception:
                logger.exception("LAN Cowork background init failed")

        @app.before_serving
        async def _init():
            # Run cowork startup in the background so the HTTP server becomes
            # ready immediately. Previously we awaited _start_cowork() here,
            # which serially attempted /api/peer/heartbeat + /api/peer/register
            # against every cached peer; with offline peers each request hit
            # the 5s connect timeout, blocking Hypercorn's "ready" signal for
            # 15-30 s. Routes call _get_manager() and tolerate None until
            # initialization completes.
            import asyncio
            global _init_task
            _init_task = asyncio.create_task(_start_cowork())

        @app.after_serving
        async def _shutdown():
            global _manager, _init_task
            # If the background init is still running, wait for it (or cancel
            # it) before shutting down. Otherwise CoworkManager could finish
            # initializing AFTER _shutdown returns and leak the daemon
            # threads / sockets it owns with no stop() ever called.
            if _init_task is not None and not _init_task.done():
                _init_task.cancel()
                import contextlib
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await _init_task
            _init_task = None
            if _manager:
                await _manager.stop()
                _manager = None

    return bp


__all__ = ["get_blueprint"]
