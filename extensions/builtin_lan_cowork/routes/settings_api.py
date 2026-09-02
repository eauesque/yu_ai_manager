"""Settings endpoints for peer-auth and fleet configuration."""
from __future__ import annotations

import asyncio
import logging

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import (
    FleetAllowlistsUpdateRequest,
    FleetSettingsUpdateRequest,
    PeerAuthSettingsUpdateRequest,
)

_EXT_NAME = "builtin-lan-cowork"
_AUTH_PREFIX = "/ext/lan_cowork"

def register_routes(bp: Blueprint, *, get_manager, session_guard) -> None:
    @auth_route(bp, "/api/settings/peer-auth", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def get_peer_auth_settings():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
        values = await asyncio.to_thread(
            lambda: {
                "protect_heartbeat": bool(get_extension_config_value(_EXT_NAME, "protect_heartbeat", True)),
                "protect_events": bool(get_extension_config_value(_EXT_NAME, "protect_events", True)),
                "allowed_cidr": int(get_extension_config_value(_EXT_NAME, "allowed_cidr", 24)),
            }
        )
        return jsonify({"ok": True, **values})

    @auth_route(bp, "/api/settings/peer-auth", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def update_peer_auth_settings():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, PeerAuthSettingsUpdateRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        payload = data.model_dump(exclude_none=True)
        to_save: dict = {}
        for bool_key in ("protect_heartbeat", "protect_events"):
            if bool_key in payload:
                to_save[bool_key] = payload[bool_key]
        if "allowed_cidr" in payload:
            to_save["allowed_cidr"] = payload["allowed_cidr"]
        from core.extensions_core.lifecycle.extensions_admin import save_extension_config_values
        await asyncio.to_thread(save_extension_config_values, _EXT_NAME, to_save)
        mgr = get_manager()
        if mgr is not None and hasattr(mgr, "config") and isinstance(mgr.config, dict):
            mgr.config.update(to_save)

        return jsonify({"ok": True})

    @auth_route(bp, "/api/settings/fleet", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def get_fleet_settings():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
        fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
        fleet_cfg = fleet_cfg or {}
        return jsonify({"ok": True, "chief": bool(fleet_cfg.get("chief", False))})

    @auth_route(bp, "/api/settings/fleet", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def update_fleet_settings():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, FleetSettingsUpdateRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        chief = data.chief
        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
            save_extension_config_values,
        )
        fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
        fleet_cfg = dict(fleet_cfg or {})
        fleet_cfg["chief"] = chief
        await asyncio.to_thread(save_extension_config_values, _EXT_NAME, {"fleet": fleet_cfg})

        mgr = get_manager()
        if mgr is not None:
            mgr.config.setdefault("fleet", {})["chief"] = chief
            import asyncio as _asyncio
            if chief:
                mgr.local_peer.roles = ["chief"]
                if mgr._fleet_manager is None:
                    from ..core_impl.fleet.fleet_manager import FleetManager
                    mgr._fleet_manager = FleetManager(mgr)

                async def _start_with_observation(fm, m):
                    demoted = await fm.observe_and_maybe_demote()
                    if demoted:
                        m._fleet_manager = None
                    else:
                        await fm.start()
                _asyncio.ensure_future(_start_with_observation(mgr._fleet_manager, mgr))
            else:
                mgr.local_peer.roles = []
                if mgr._fleet_manager is not None:
                    fm = mgr._fleet_manager
                    mgr._fleet_manager = None
                    _asyncio.ensure_future(fm.stop())

        return jsonify({"ok": True, "chief": chief})

    _ALLOWLIST_KEYS = ("allow_log_stream_from", "allow_update_from", "allow_restart_from")

    def _normalize_allowlist(entries) -> list[str]:
        out: list[str] = []
        if not isinstance(entries, list):
            return out
        for e in entries:
            if isinstance(e, str) and e.strip():
                out.append(e.strip())
            elif isinstance(e, dict) and isinstance(e.get("peer_id"), str) and e["peer_id"].strip():
                out.append(e["peer_id"].strip())
        seen = set()
        result = []
        for pid in out:
            if pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    @auth_route(bp, "/api/settings/fleet/allowlists", methods=["GET"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def get_fleet_allowlists():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
        fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
        fleet_cfg = fleet_cfg or {}
        return jsonify({
            "ok": True,
            "allow_log_stream_from": _normalize_allowlist(fleet_cfg.get("allow_log_stream_from", [])),
            "allow_update_from": _normalize_allowlist(fleet_cfg.get("allow_update_from", [])),
            "allow_restart_from": _normalize_allowlist(fleet_cfg.get("allow_restart_from", [])),
            "allow_remote_update": bool(fleet_cfg.get("allow_remote_update", True)),
        })

    @auth_route(bp, "/api/settings/fleet/allowlists", methods=["POST"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def update_fleet_allowlists():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        data, err = await require_json_model(request, FleetAllowlistsUpdateRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        payload = data.model_dump(exclude_none=True)

        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
            save_extension_config_values,
        )
        fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
        old_fleet_cfg = dict(fleet_cfg or {})
        fleet_cfg = dict(fleet_cfg or {})

        for key in _ALLOWLIST_KEYS:
            if key in payload:
                fleet_cfg[key] = _normalize_allowlist(payload[key])

        if "allow_remote_update" in payload:
            fleet_cfg["allow_remote_update"] = payload["allow_remote_update"]

        await asyncio.to_thread(save_extension_config_values, _EXT_NAME, {"fleet": fleet_cfg})

        mgr = get_manager()
        if mgr is not None and hasattr(mgr, "config") and isinstance(mgr.config, dict):
            mgr.config.setdefault("fleet", {}).update({
                k: fleet_cfg[k] for k in (*_ALLOWLIST_KEYS, "allow_remote_update")
                if k in fleet_cfg
            })

        try:
            from quart import session as _sess
            sess_id = _sess.get("pin_session_id", "unknown")
            from core.services_core.agent_action_journal_service import (
                log_fleet_master_switch,
                log_fleet_permission_change,
            )
            old_master = bool(old_fleet_cfg.get("allow_remote_update", False))
            new_master = bool(fleet_cfg.get("allow_remote_update", False))
            if old_master != new_master:
                log_fleet_master_switch(sess_id, before=old_master, after=new_master)
            old_update = set(_normalize_allowlist(old_fleet_cfg.get("allow_update_from", []) or []))
            old_restart = set(_normalize_allowlist(old_fleet_cfg.get("allow_restart_from", []) or []))
            old_log = set(_normalize_allowlist(old_fleet_cfg.get("allow_log_stream_from", []) or []))
            new_update = set(_normalize_allowlist(fleet_cfg.get("allow_update_from", []) or []))
            new_restart = set(_normalize_allowlist(fleet_cfg.get("allow_restart_from", []) or []))
            new_log = set(_normalize_allowlist(fleet_cfg.get("allow_log_stream_from", []) or []))
            all_pids = old_update | new_update | old_restart | new_restart | old_log | new_log
            for pid in all_pids:
                before_p = {
                    "restart": pid in old_restart or pid in old_update,
                    "update": pid in old_update,
                    "log_stream": pid in old_log,
                }
                after_p = {
                    "restart": pid in new_restart or pid in new_update,
                    "update": pid in new_update,
                    "log_stream": pid in new_log,
                }
                if before_p != after_p:
                    log_fleet_permission_change(sess_id, pid, before_p, after_p)
        except Exception as _audit_err:
            logging.getLogger(__name__).debug("fleet permission audit log failed: %s", _audit_err)

        return jsonify({
            "ok": True,
            "allow_log_stream_from": fleet_cfg.get("allow_log_stream_from", []),
            "allow_update_from": fleet_cfg.get("allow_update_from", []),
            "allow_restart_from": fleet_cfg.get("allow_restart_from", []),
            "allow_remote_update": bool(fleet_cfg.get("allow_remote_update", True)),
        })


    # Registered at the root by _register_fleet_allowlists_internal_route below,
    # not with @bp.route: see the comment there.
    async def _internal_fleet_allowlists_changed():
        """Internal notify endpoint called by Rust after fleet allowlists config mutations."""
        from core.web.auth_helpers import require_local

        err = require_local("fleet-allowlists-changed notify")
        if err:
            return err
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        try:
            from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

            fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
            mgr.config["fleet"] = dict(fleet_cfg or {})
        except Exception:
            logging.getLogger(__name__).exception("fleet-allowlists-changed reload failed")
            return jsonify({"ok": False, "error": "reload failed"}), 503
        return jsonify({"ok": True})

    @bp.record_once
    def _register_fleet_allowlists_internal_route(state):
        # Root-level, not @bp.route: this blueprint is mounted at
        # /ext/lan_cowork (extensions_manager_register derives the prefix from
        # the extension name when extension.json declares none), so a plain
        # @bp.route would serve this at /ext/lan_cowork/_internal/... while the
        # Rust caller posts to /_internal/... — every notify 404ed and the
        # calling route answered 502 "live sync failed".
        state.app.add_url_rule(
            "/_internal/lan_cowork/fleet-allowlists-changed",
            endpoint="lan_cowork_fleet_allowlists_changed_internal",
            view_func=_internal_fleet_allowlists_changed,
            methods=["POST"],
        )

    # Registered at the root by _register_fleet_chief_internal_route below,
    # not with @bp.route: see the comment on the allowlists registration.
    async def _internal_fleet_chief_changed():
        """Internal notify endpoint called by Rust after fleet chief config mutations."""
        from core.web.auth_helpers import require_local

        err = require_local("fleet-chief-changed notify")
        if err:
            return err
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        try:
            from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value

            fleet_cfg = await asyncio.to_thread(get_extension_config_value, _EXT_NAME, "fleet", {})
            fleet_cfg = fleet_cfg or {}
            chief = bool(fleet_cfg.get("chief", False))
            mgr.config.setdefault("fleet", {})["chief"] = chief
            already = (chief and mgr._fleet_manager is not None) or (
                not chief and mgr._fleet_manager is None
            )
            if already:
                return jsonify({"ok": True, "unchanged": True})
            import asyncio as _asyncio

            if chief:
                mgr.local_peer.roles = ["chief"]
                if mgr._fleet_manager is None:
                    from ..core_impl.fleet.fleet_manager import FleetManager

                    mgr._fleet_manager = FleetManager(mgr)

                async def _start_with_observation(fm, m):
                    demoted = await fm.observe_and_maybe_demote()
                    if demoted:
                        m._fleet_manager = None
                    else:
                        await fm.start()

                _asyncio.ensure_future(_start_with_observation(mgr._fleet_manager, mgr))
            else:
                mgr.local_peer.roles = []
                if mgr._fleet_manager is not None:
                    fm = mgr._fleet_manager
                    mgr._fleet_manager = None
                    _asyncio.ensure_future(fm.stop())
        except Exception:
            logging.getLogger(__name__).exception("fleet-chief-changed reload failed")
            return jsonify({"ok": False, "error": "reload failed"}), 503
        return jsonify({"ok": True})

    @bp.record_once
    def _register_fleet_chief_internal_route(state):
        state.app.add_url_rule(
            "/_internal/lan_cowork/fleet-chief-changed",
            endpoint="lan_cowork_fleet_chief_changed_internal",
            view_func=_internal_fleet_chief_changed,
            methods=["POST"],
        )

    _my_perm_cache: dict[str, tuple[dict, float]] = {}
    _MY_PERM_TTL = 10.0
    _MY_PERM_SEM = asyncio.Semaphore(10)

    @auth_route(bp, "/api/settings/fleet/my-permissions", methods=["GET"],
                absolute_prefix=_AUTH_PREFIX, require="session")
    async def get_my_permissions():
        if not session_guard():
            return jsonify({"ok": False, "error": "session required"}), 401
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503

        import time as _time

        from extensions.builtin_lan_cowork.core_impl.fleet import fleet_peer_http as _fph

        bust = "bust" in request.args
        now = _time.monotonic()

        paired = [
            p for p in mgr.registry.list_all()
            if p.peer_id != mgr.local_peer.peer_id
            and getattr(p, "token", None)
            and (getattr(p, "token_expires_at", None) is None
                 or p.token_expires_at > _time.time())
        ]

        async def _fetch_one(peer) -> dict:
            base = {
                "peer_id": peer.peer_id,
                "name": getattr(peer, "name", peer.peer_id),
                "status": getattr(peer, "status", "unknown"),
            }
            null_fields = {"restart": None, "update": None, "log_stream": None, "allow_remote_update": None}

            if not bust and peer.peer_id in _my_perm_cache:
                cached, expire = _my_perm_cache[peer.peer_id]
                if now < expire:
                    return cached

            if getattr(peer, "status", "") != "online":
                return {**base, **null_fields, "error": "peer_offline"}

            async with _MY_PERM_SEM:
                try:
                    body, status_code = await asyncio.wait_for(
                        _fph.fetch_peer_allowlist_status(mgr, peer), timeout=3.0
                    )
                except TimeoutError:
                    return {**base, **null_fields, "error": "timeout"}
                except Exception:
                    return {**base, **null_fields, "error": "peer_unreachable"}

            if status_code == 409:
                return {**base, **null_fields, "error": "no_pairing_token"}
            if status_code in (401, 403):
                return {**base, **null_fields, "error": "auth_failed"}
            if not body.get("ok"):
                return {**base, **null_fields, "error": "peer_unreachable"}

            result = {
                **base,
                "restart": bool(body.get("restart")),
                "update": bool(body.get("update")),
                "log_stream": bool(body.get("log_stream")),
                "allow_remote_update": bool(body.get("allow_remote_update")),
                "error": None,
            }
            _my_perm_cache[peer.peer_id] = (result, now + _MY_PERM_TTL)
            return result

        results = await asyncio.gather(*[_fetch_one(p) for p in paired])
        return jsonify({"ok": True, "peers": list(results)})
