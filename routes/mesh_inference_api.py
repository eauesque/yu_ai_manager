"""/api/mesh-inference/* — per-peer-per-type disable matrix.

Exposes:
  GET  /api/mesh-inference/state    — full matrix + disabled flags
  POST /api/mesh-inference/toggle   — single (peer_id, inference_type) flip
  POST /api/mesh-inference/bulk     — disable_all_remote / enable_all / local_only
  POST /api/mesh-inference/refresh  — kick discovery refresh (mDNS)

State lives in core.mesh_inference.state.MeshInferenceState, backed by
data/mesh_inference_state.json.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from quart import Blueprint, current_app, request

logger = logging.getLogger(__name__)

from core.infra_core.api_errors import api_error, api_result
from core.mesh_inference import get_router, has_mesh, persistence
from core.mesh_inference.state import get_state

bp = Blueprint("mesh_inference_api", __name__)

# Canonical inference_type universe. Keep in sync with
# extensions/builtin_lan_cowork/core_impl/inference/state.py get_inference_types()
KNOWN_TYPES = ("tagger", "clip", "yolo", "whisper")

# Per-action debounce for /api/mesh-inference/bulk (1 second window).
# Prevents rapid-fire API calls from toggling all remote peers repeatedly.
_bulk_last_call: dict[str, float] = {}
_BULK_DEBOUNCE_SEC = 1.0


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _persist_current_state() -> None:
    persistence.save_state(get_state().snapshot())


def _peer_row(peer, is_local: bool) -> dict[str, Any]:
    advertised = list(peer.inference_types or [])
    disabled = sorted(
        t for t in advertised
        if get_state().is_disabled(peer.peer_id, t)
    )
    return {
        "peer_id": peer.peer_id,
        "name": peer.name,
        "status": peer.status,
        "is_local": is_local,
        "inference_types": advertised,
        "device_info": getattr(peer, "gpu", "") or "",
        "disabled_types": disabled,
    }


def _collect_all_peers() -> list[dict[str, Any]]:
    if not has_mesh():
        return []
    router = get_router()
    local = router._local_peer
    rows = [_peer_row(local, is_local=True)]
    try:
        remote = router._registry.list_online()
    except Exception:
        remote = []
    for p in remote:
        rows.append(_peer_row(p, is_local=False))
    return rows


@bp.route("/api/mesh-inference/state", methods=["GET"])
async def api_state():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    peers = _collect_all_peers()
    return api_result({"peers": peers})


def _find_peer(peer_id: str):
    """Look up a PeerInfo by peer_id across local + registered peers.

    Returns (peer, is_local) or (None, False). Accepts both online and
    offline remote peers — PeerRegistry.list_online() excludes offline,
    so we also scan the full registry via its .peers attribute when present.
    """
    router = get_router()
    if router is None:
        return None, False
    local = router._local_peer
    if peer_id == local.peer_id:
        return local, True
    # Try registry's full enumeration. PeerRegistry exposes list_online();
    # when offline is needed, fall back to iterating ._peers if available.
    reg = router._registry
    online = []
    try:
        online = reg.list_online()
    except Exception:
        online = []
    for p in online:
        if p.peer_id == peer_id:
            return p, False
    all_peers = getattr(reg, "_peers", None)
    if isinstance(all_peers, dict) and peer_id in all_peers:
        return all_peers[peer_id], False
    return None, False


@bp.route("/api/mesh-inference/toggle", methods=["POST"])
async def api_toggle():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    from core.mesh_inference.peer_id import is_valid_peer_id

    data = await request.get_json(silent=True) or {}
    peer_id = data.get("peer_id")
    inference_type = data.get("inference_type")
    disabled = data.get("disabled", False)

    if not isinstance(peer_id, str) or not is_valid_peer_id(peer_id):
        return api_error("invalid peer_id", 400, code="invalid_peer_id")
    if inference_type not in KNOWN_TYPES:
        return api_error(
            f"unknown inference_type: {inference_type!r}",
            400,
            code="unknown_inference_type",
        )
    if not isinstance(disabled, bool):
        return api_error("disabled must be a boolean", 400, code="invalid_disabled")

    peer, _ = _find_peer(peer_id)
    if peer is None:
        return api_error("unknown peer", 404, code="unknown_peer")

    advertised = list(peer.inference_types or [])
    if inference_type not in advertised:
        return api_error(
            f"peer {peer_id!r} does not advertise {inference_type!r}",
            400,
            code="type_not_advertised",
        )

    try:
        get_state().set_disabled(peer_id, inference_type, disabled)
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_peer_id")

    _persist_current_state()
    return api_result({
        "peer_id": peer_id,
        "inference_type": inference_type,
        "disabled": disabled,
    })


def _local_is_effective() -> bool:
    """Return True iff local peer has at least one advertised type that is
    not currently disabled. Mirrors the UI button guard.
    """
    router = get_router()
    if router is None:
        return False
    local = router._local_peer
    state = get_state()
    return any(
        t in (local.inference_types or [])
        and not state.is_disabled(local.peer_id, t)
        for t in KNOWN_TYPES
    )


@bp.route("/api/mesh-inference/bulk", methods=["POST"])
async def api_bulk():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    data = await request.get_json(silent=True) or {}
    action = data.get("action")
    inference_type = data.get("inference_type")

    if not has_mesh():
        return api_result({"changed": 0})

    if action == "local_only" and not _local_is_effective():
        return api_error(
            "local peer has no effective inference types",
            409,
            code="local_peer_has_no_effective_types",
        )

    # Debounce: reject rapid-fire calls with the same action within 1 second
    if not current_app.config.get("TESTING", False):
        now = time.monotonic()
        debounce_key = f"{action}:{inference_type}"
        last = _bulk_last_call.get(debounce_key, 0.0)
        if now - last < _BULK_DEBOUNCE_SEC:
            return api_error(
                "too many requests, please wait",
                429,
                code="bulk_debounce",
            )
        _bulk_last_call[debounce_key] = now

    get_router()
    peers = _collect_all_peers()
    state = get_state()
    changed = 0

    if action == "disable_all_remote":
        if inference_type not in KNOWN_TYPES:
            return api_error(
                "inference_type required",
                400,
                code="unknown_inference_type",
            )
        for row in peers:
            if row["is_local"]:
                continue
            if inference_type not in row["inference_types"]:
                continue
            if not state.is_disabled(row["peer_id"], inference_type):
                try:
                    state.set_disabled(row["peer_id"], inference_type, True)
                    changed += 1
                except ValueError:
                    logger.warning(
                        "api_bulk: skipping invalid peer_id %r in disable_all_remote",
                        row["peer_id"],
                    )

    elif action == "enable_all":
        if inference_type not in KNOWN_TYPES:
            return api_error(
                "inference_type required",
                400,
                code="unknown_inference_type",
            )
        for row in peers:
            if state.is_disabled(row["peer_id"], inference_type):
                try:
                    state.set_disabled(row["peer_id"], inference_type, False)
                    changed += 1
                except ValueError:
                    logger.warning(
                        "api_bulk: skipping invalid peer_id %r in enable_all",
                        row["peer_id"],
                    )

    elif action == "local_only":
        for row in peers:
            if row["is_local"]:
                continue
            for t in row["inference_types"]:
                if not state.is_disabled(row["peer_id"], t):
                    try:
                        state.set_disabled(row["peer_id"], t, True)
                        changed += 1
                    except ValueError:
                        logger.warning(
                            "api_bulk: skipping invalid peer_id %r in local_only",
                            row["peer_id"],
                        )

    else:
        return api_error(
            f"unknown action: {action!r}", 400, code="unknown_action"
        )

    _persist_current_state()
    return api_result({"changed": changed})


@bp.route("/api/mesh-inference/refresh", methods=["POST"])
async def api_refresh():
    """Re-read the peer list and return the fresh matrix.

    Does NOT trigger an active mDNS probe — the mDNS browser runs
    continuously in the background. This endpoint exists to let clients
    force a state.json re-read without hitting GET /state (cleaner semantic).
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    peers = _collect_all_peers()
    return api_result({"peers": peers})
