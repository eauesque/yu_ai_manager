"""extensions/builtin_lan_cowork/routes/peer_api.py
REST endpoints for peer discovery, pairing, and status.
"""
from __future__ import annotations

import base64
import time

from quart import Blueprint, jsonify, request

from core.infra_core.api_request import require_json_model
from core.web.auth_route_policy import auth_route
from extensions.builtin_lan_cowork.routes.request_models import (
    PeerEventRequest,
    PeerHeartbeatRequest,
    PeerRegisterRequest,
)

_AUTH_PREFIX = "/ext/lan_cowork"

# generation.submit may carry img2img base64 data in params.
PEER_EVENT_HARD_BODY_LIMIT = 8 * 1024 * 1024
PEER_EVENT_SMALL_BODY_LIMIT = 64 * 1024


def peer_event_body_limit(event_type: str) -> int:
    """Return the maximum accepted body size for a peer relay event."""
    return PEER_EVENT_HARD_BODY_LIMIT if event_type == "generation.submit" else PEER_EVENT_SMALL_BODY_LIMIT


def peer_event_body_too_large(event_type: str, body_size: int) -> bool:
    """Return whether a peer relay event body exceeds its type-specific limit."""
    return body_size > peer_event_body_limit(event_type)


def register_routes(bp: Blueprint, get_manager, session_guard=None) -> None:
    """Register /api/peer/* routes on the given blueprint."""
    from ..core_impl.peer_auth import require_peer_auth, require_peer_renew_auth

    _auth = require_peer_auth(get_manager)
    _renew_auth = require_peer_renew_auth(get_manager)

    def _session_ok() -> bool:
        if session_guard is not None:
            return session_guard()
        try:
            from quart import current_app
            from quart import session as _s
            if not current_app.config.get("PIN_AUTH"):
                return True
            return bool(_s.get("pin_ok"))
        except Exception:
            return False

    def _serialize_peer(peer):
        if _session_ok():
            d = peer.to_dict()
            mgr = get_manager()
            if mgr is not None and hasattr(mgr, "token_store"):
                d["has_inbound_token"] = mgr.token_store.has_token(peer.peer_id)
            return d
        return peer.to_public_dict()

    # --- Public endpoints (no auth — used for initial handshake) ---

    @auth_route(bp, "/api/peer/discover", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    async def peer_discover():
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        local_id = mgr.local_peer.peer_id
        peers = [
            _serialize_peer(p)
            for p in mgr.registry.list_all()
            if p.peer_id != local_id
        ]
        return jsonify({"ok": True, "peers": peers})

    @auth_route(bp, "/api/peer/status", methods=["GET"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    async def peer_status():
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        local = mgr.local_peer
        return jsonify({
            "ok": True,
            "peer": _serialize_peer(local),
            "pubkey": base64.b64encode(local.pubkey).decode() if local.pubkey else None,
            "x25519_pk": base64.b64encode(local.x25519_pk).decode() if local.x25519_pk else None,
        })

    @auth_route(bp, "/api/peer/register", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    async def peer_register():
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        data, err = await require_json_model(request, PeerRegisterRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        host = data.host
        port = data.port
        # Validate host is a private/link-local IP (SSRF prevention)
        import ipaddress
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return jsonify({"ok": False, "error": "invalid IP address"}), 400
        if not (addr.is_private or addr.is_link_local):
            return jsonify({"ok": False, "error": "only private/link-local addresses allowed"}), 400
        if addr.is_loopback:
            return jsonify({"ok": False, "error": "loopback address not allowed"}), 400
        from ..core_impl.models import PeerInfo
        temp = PeerInfo(name="temp", api_host=host, api_port=port)
        ok, info = await mgr.transport.fetch_json(temp, "/api/peer/status")
        if not ok:
            return jsonify({"ok": False, "error": "peer not reachable"}), 502
        peer = PeerInfo.from_dict(info.get("peer", {}))
        peer.api_host = host
        peer.api_port = port
        # Preserve pairing fields — /api/peer/status never returns tokens,
        # so constructing from it would overwrite a valid token with NULL.
        existing = mgr.registry.get(peer.peer_id)
        if existing is not None:
            peer.token = existing.token
            peer.token_expires_at = existing.token_expires_at
            peer.token_issued_at = existing.token_issued_at
        mgr.registry.upsert(peer)
        return jsonify({"ok": True, "peer": peer.to_public_dict()})

    # --- Authenticated endpoints (require registered peer + IP match) ---

    @auth_route(bp, "/api/peer/heartbeat", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_heartbeat():
        mgr = get_manager()
        data, err = await require_json_model(request, PeerHeartbeatRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        peer_id = request.headers.get("X-Peer-Id", "")
        updated = mgr.registry.update_runtime(
            peer_id,
            generating=data.generating,
            queue_depth=data.queue_depth,
            bridges=data.bridges,
            inference_types=data.inference_types,
            last_seen=time.time(),
            status="online",
        )
        if updated is None:
            return jsonify({"ok": False, "error": "unknown peer"}), 403
        return jsonify({"ok": True})

    @auth_route(bp, "/api/peer/event", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_auth
    async def peer_event():
        mgr = get_manager()
        data, err = await require_json_model(request, PeerEventRequest)
        if err:
            return jsonify({"ok": False, **err[0]}), err[1]
        assert data is not None
        event_type = data.event_type
        event_data = data.event_data
        body_size = request.content_length
        if body_size is None:
            body_size = len(await request.get_data(cache=True))
        if peer_event_body_too_large(event_type, body_size):
            return jsonify({"ok": False, "error": "event body too large"}), 413
        # The body field is wire-compatible but not trustworthy; auth verified this header.
        source_peer = request.headers.get("X-Peer-Id", "").strip()
        accepted = mgr.event_relay.inject_remote_event(event_type, event_data, source_peer)
        if not accepted:
            return jsonify({"ok": False, "error": "event type not allowed"}), 403
        return jsonify({"ok": True})

    @auth_route(bp, "/api/peer/token/renew", methods=["POST"], absolute_prefix=_AUTH_PREFIX, bypass_session=True, require="peer")
    @_renew_auth
    async def peer_token_renew():
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        peer_id = request.headers.get("X-Peer-Id", "").strip()
        ok, token, expires_at = mgr.token_store.renew_if_not_revoked(peer_id)
        if not ok:
            return jsonify({"ok": False, "error": "token has been revoked"}), 403
        return jsonify({"ok": True, "token": token, "expires_at": expires_at})

    @auth_route(bp, "/api/peer/<peer_id>", methods=["DELETE"], absolute_prefix=_AUTH_PREFIX, require="peer")
    @_auth
    async def peer_delete(peer_id: str):
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        mgr.registry.remove(peer_id)
        return jsonify({"ok": True})

    @auth_route(bp, "/api/peer/admin/<peer_id>", methods=["DELETE"], absolute_prefix=_AUTH_PREFIX, require="session")
    async def peer_admin_delete(peer_id: str):
        """Session-authenticated peer removal (used from the LAN Cowork UI)."""
        if not _session_ok():
            return jsonify({"ok": False, "error": "session required"}), 401
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        if peer_id == mgr.local_peer.peer_id:
            return jsonify({"ok": False, "error": "cannot remove self"}), 400
        mgr.registry.remove(peer_id)

        # Remove peer_id from all fleet allowlists
        try:
            from core.extensions_core.lifecycle.extensions_admin import (
                get_extension_config_value,
                save_extension_config_values,
            )

            def _to_str_list(raw) -> list[str]:
                """Normalize a raw allowlist (str or {peer_id: ...} dict entries) to a list of strings."""
                out = []
                if not isinstance(raw, list):
                    return out
                for e in raw:
                    if isinstance(e, str) and e.strip():
                        out.append(e.strip())
                    elif isinstance(e, dict) and isinstance(e.get("peer_id"), str):
                        out.append(e["peer_id"].strip())
                return list(dict.fromkeys(out))  # dedupe preserving order

            _EXT = "builtin-lan-cowork"
            f_cfg = dict(get_extension_config_value(_EXT, "fleet", {}) or {})
            changed = False
            for _key in ("allow_log_stream_from", "allow_update_from", "allow_restart_from"):
                raw = f_cfg.get(_key, []) or []
                entries = _to_str_list(raw)  # normalize to str before comparison
                if peer_id in entries:
                    f_cfg[_key] = [e for e in entries if e != peer_id]
                    changed = True
            if changed:
                save_extension_config_values(_EXT, {"fleet": f_cfg})
                if mgr is not None and hasattr(mgr, "config"):
                    for _key in ("allow_log_stream_from", "allow_update_from", "allow_restart_from"):
                        if _key in f_cfg:
                            mgr.config.setdefault("fleet", {})[_key] = f_cfg[_key]
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("allowlist cleanup after peer delete failed: %s", _e)

        return jsonify({"ok": True})

    @bp.record_once
    def _register_registry_peer_changed_internal_route(state):
        # Root-level, not @bp.route: this blueprint is mounted at
        # /ext/lan_cowork, so a plain @bp.route would serve this at
        # /ext/lan_cowork/_internal/... while the Rust caller posts to
        # /_internal/... — every notify 404ed and peer_admin_delete answered
        # 502 "live sync failed" with the config change already persisted.
        state.app.add_url_rule(
            "/_internal/lan_cowork/registry-peer-changed",
            endpoint="lan_cowork_registry_peer_changed_internal",
            view_func=_internal_registry_peer_changed,
            methods=["POST"],
        )
    async def _internal_registry_peer_changed():
        """Internal notify called by the Rust server after peer registry
        mutations (token revoke / admin delete) so the live in-memory registry
        stays in sync. Rust owns the DB rows; this only touches in-memory state."""
        from core.web.auth_helpers import require_local

        err = require_local("registry-peer-changed notify")
        if err:
            return err
        mgr = get_manager()
        if mgr is None:
            return jsonify({"ok": False, "error": "LAN Cowork not enabled"}), 503
        data = await request.get_json(silent=True) or {}
        peer_id = (data.get("peer_id") or "").strip()
        action = (data.get("action") or "").strip()
        if not peer_id:
            return jsonify({"ok": False, "error": "peer_id required"}), 400
        registry = getattr(mgr, "registry", None)
        if registry is None:
            return jsonify({"ok": False, "error": "registry unavailable"}), 503
        if action == "removed":
            registry.remove(peer_id)
        elif action == "token_cleared":
            try:
                import dataclasses as _dc
                peer = registry.get(peer_id)
                if peer is not None:
                    registry.upsert(
                        _dc.replace(
                            peer, token=None, token_expires_at=None, token_issued_at=None
                        )
                    )
            except Exception:
                import logging
                logging.getLogger(__name__).debug(
                    "registry token clear failed", exc_info=True
                )
        else:
            return jsonify({"ok": False, "error": "unknown action"}), 400
        return jsonify({"ok": True})
