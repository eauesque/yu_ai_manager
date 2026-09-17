"""Allowlist-related fleet route registrations."""
from __future__ import annotations

import asyncio

from quart import jsonify, request

from core.infra_core.api_request import require_json_dict
from core.web.auth_route_policy import auth_route

from .fleet_route_deps import FleetAllowlistRouteDeps
from .fleet_route_guards import build_local_chief_getter, build_manager_getter

_AUTH_PREFIX = "/ext/lan_cowork"


def _require_string_categories(
    value,
    *,
    require_non_empty: bool = False,
):
    # Peer input type gate only; persistent allowlist normalization remains below.
    categories = value
    if not isinstance(categories, list) or (require_non_empty and not categories):
        return None, ({"ok": False, "error": "categories required"}, 400)
    if any(not isinstance(item, str) for item in categories):
        return None, ({"ok": False, "error": "categories must be a list of strings"}, 400)
    return categories, None


def register_fleet_allowlist_routes(
    bp,
    get_manager,
    deps: FleetAllowlistRouteDeps,
):
    auth_decorator = deps.auth_decorator
    session_ok = deps.session_ok
    allowlist_categories = deps.allowlist_categories
    normalize_entries = deps.normalize_entries
    apply_allowlist_update = deps.apply_allowlist_update
    proxy_allowlist_to_peer = deps.proxy_allowlist_to_peer
    fetch_peer_allowlist_status = deps.fetch_peer_allowlist_status

    require_manager = build_manager_getter(get_manager)
    require_local_chief = build_local_chief_getter(require_manager, session_ok, ok_key=True)

    @auth_route(bp, "/fleet/allowlists/grant", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @auth_decorator
    async def fleet_allowlists_grant():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]
        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()

        data, err = await require_json_dict(request)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        categories, cat_err = _require_string_categories(
            data.get("categories"),
            require_non_empty=True,
        )
        if cat_err:
            return jsonify(cat_err[0]), cat_err[1]
        assert categories is not None
        invalid = [c for c in categories if c not in allowlist_categories]
        if invalid:
            return jsonify({"ok": False, "error": f"invalid categories: {invalid}"}), 400

        def mutate(cfg: dict) -> None:
            for cat in categories:
                key = allowlist_categories[cat]
                entries = list(cfg.get(key, []))
                if requester_peer_id not in entries:
                    entries.append(requester_peer_id)
                cfg[key] = entries

        fleet_cfg = await asyncio.to_thread(apply_allowlist_update, mgr, mutate)
        return jsonify({
            "ok": True,
            "granted_to": requester_peer_id,
            "categories": categories,
            "allow_log_stream_from": fleet_cfg.get("allow_log_stream_from", []),
            "allow_update_from": fleet_cfg.get("allow_update_from", []),
            "allow_remote_update": bool(fleet_cfg.get("allow_remote_update", False)),
        })

    @auth_route(bp, "/fleet/allowlists/revoke", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @auth_decorator
    async def fleet_allowlists_revoke():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]
        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()

        data, err = await require_json_dict(request)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        raw_categories = data.get("categories")
        categories_value = (
            list(allowlist_categories.keys())
            if raw_categories is None or raw_categories == []
            else raw_categories
        )
        categories, cat_err = _require_string_categories(categories_value)
        if cat_err:
            return jsonify(cat_err[0]), cat_err[1]
        assert categories is not None
        invalid = [c for c in categories if c not in allowlist_categories]
        if invalid:
            return jsonify({"ok": False, "error": f"invalid categories: {invalid}"}), 400

        def mutate(cfg: dict) -> None:
            for cat in categories:
                key = allowlist_categories[cat]
                entries = [p for p in cfg.get(key, []) if p != requester_peer_id]
                cfg[key] = entries

        fleet_cfg = await asyncio.to_thread(apply_allowlist_update, mgr, mutate)
        return jsonify({
            "ok": True,
            "revoked_from": requester_peer_id,
            "categories": categories,
            "allow_log_stream_from": fleet_cfg.get("allow_log_stream_from", []),
            "allow_update_from": fleet_cfg.get("allow_update_from", []),
        })

    @auth_route(bp, "/fleet/allowlists/check", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @auth_decorator
    async def fleet_allowlists_check():
        mgr, failure = require_manager()
        if failure:
            return jsonify(failure[0]), failure[1]
        requester_peer_id = request.headers.get("X-Peer-Id", "").strip()

        fleet_cfg = mgr.config.get("fleet") or {}
        log_entries = normalize_entries(fleet_cfg.get("allow_log_stream_from", []))
        upd_entries = normalize_entries(fleet_cfg.get("allow_update_from", []))
        rst_entries = normalize_entries(fleet_cfg.get("allow_restart_from", []))
        restart_ok = requester_peer_id in upd_entries or requester_peer_id in rst_entries
        return jsonify({
            "ok": True,
            "requester_peer_id": requester_peer_id,
            "peer_id": requester_peer_id,  # deprecated: same value; removed in v4.118.x
            "restart": restart_ok,
            "update": requester_peer_id in upd_entries,
            "log_stream": requester_peer_id in log_entries,
            "allow_remote_update": bool(fleet_cfg.get("allow_remote_update", False)),
        })

    @bp.route("/fleet/peer-grant", methods=["POST"])
    async def fleet_peer_grant():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        data, err = await require_json_dict(request)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        target_peer_id = (data.get("peer_id") or "").strip()
        categories = data.get("categories") or ["log_stream", "update"]
        if not target_peer_id:
            return jsonify({"ok": False, "error": "peer_id required"}), 400
        peer = mgr.registry.get(target_peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer_not_found"}), 404

        body, status = await proxy_allowlist_to_peer(mgr, peer, action="grant", categories=categories)
        return jsonify(body), status

    @bp.route("/fleet/peer-revoke", methods=["POST"])
    async def fleet_peer_revoke():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        data, err = await require_json_dict(request)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        target_peer_id = (data.get("peer_id") or "").strip()
        categories = data.get("categories") or ["log_stream", "update"]
        if not target_peer_id:
            return jsonify({"ok": False, "error": "peer_id required"}), 400
        peer = mgr.registry.get(target_peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer_not_found"}), 404

        body, status = await proxy_allowlist_to_peer(mgr, peer, action="revoke", categories=categories)
        return jsonify(body), status

    @bp.route("/fleet/peer-allowlist-status", methods=["GET"])
    async def fleet_peer_allowlist_status():
        mgr, failure = require_local_chief()
        if failure:
            return jsonify(failure[0]), failure[1]

        target_peer_id = (request.args.get("peer_id") or "").strip()
        if not target_peer_id:
            return jsonify({"ok": False, "error": "peer_id required"}), 400
        peer = mgr.registry.get(target_peer_id)
        if peer is None:
            return jsonify({"ok": False, "error": "peer_not_found"}), 404

        body, status = await fetch_peer_allowlist_status(mgr, peer)
        return jsonify(body), status
