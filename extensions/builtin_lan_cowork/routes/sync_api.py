"""extensions/builtin_lan_cowork/routes/sync_api.py
REST endpoints for file sync between peers.
"""
from __future__ import annotations

import base64

from quart import Blueprint, jsonify, request, send_file

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import PeerSyncNotifyRequest, PeerSyncPushRequest

_AUTH_PREFIX = "/ext/lan_cowork"


def _safe_resolve(mgr, rel_path: str):
    """Validate rel_path stays within wc_root. Returns resolved Path or None."""
    from ..core_impl.sync_manager import _validate_sync_path
    try:
        return _validate_sync_path(mgr.sync._wc_root, rel_path)
    except ValueError:
        return None


def register_routes(bp: Blueprint, get_manager) -> None:
    from ..core_impl.peer_auth import require_peer_auth

    _auth = require_peer_auth(get_manager)

    @auth_route(bp, "/api/peer/sync/manifest", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def sync_manifest():
        mgr = get_manager()
        if mgr is None or mgr.sync is None:
            return jsonify({"ok": False, "error": "sync not available"}), 503
        manifest = mgr.sync.local_manifest()
        return jsonify({"ok": True, "manifest": manifest})

    @auth_route(bp, "/api/peer/sync/file", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def sync_file():
        mgr = get_manager()
        if mgr is None or mgr.sync is None:
            return jsonify({"ok": False, "error": "sync not available"}), 503
        rel_path = request.args.get("path", "").strip()
        if not rel_path:
            return jsonify({"ok": False, "error": "invalid path"}), 400
        full_path = _safe_resolve(mgr, rel_path)
        if full_path is None:
            return jsonify({"ok": False, "error": "invalid path"}), 400
        if not full_path.is_file():
            return jsonify({"ok": False, "error": "not found"}), 404
        return await send_file(str(full_path))

    @auth_route(bp, "/api/peer/sync/push", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def sync_push():
        mgr = get_manager()
        if mgr is None or mgr.sync is None:
            return jsonify({"ok": False, "error": "sync not available"}), 503
        data, err = await require_json_model(request, PeerSyncPushRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        rel_path = data.path
        content_b64 = data.content_b64
        if _safe_resolve(mgr, rel_path) is None:
            return jsonify({"ok": False, "error": "invalid path"}), 400
        from ..core_impl.sync_manager import _write_synced_file
        content = base64.b64decode(content_b64)
        _write_synced_file(mgr.sync._wc_root, rel_path, content)
        return jsonify({"ok": True})

    @auth_route(bp, "/api/peer/sync/notify", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def sync_notify():
        mgr = get_manager()
        if mgr is None or mgr.sync is None:
            return jsonify({"ok": False, "error": "sync not available"}), 503
        data, err = await require_json_model(request, PeerSyncNotifyRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        rel_path = data.path
        peer_id = data.peer_id
        if _safe_resolve(mgr, rel_path) is None:
            return jsonify({"ok": False, "error": "invalid path"}), 400
        peer = mgr.registry.get(peer_id)
        if peer:
            await mgr.sync.handle_remote_change(peer, rel_path)
        return jsonify({"ok": True})
