"""Lightweight self-identification endpoint for mDNS peer verification.

Used by other yu_ai_manager nodes during ``LlmRouterMdnsBridge.on_peer_added``
to confirm that a node advertising ``_yu-ai._tcp.local.`` really is a
yu_ai_manager instance with the advertised node_id.

Intentionally unauthenticated: the response contains only information that
was already published via mDNS. Do NOT add any secrets or sensitive fields.
"""
from __future__ import annotations

from pathlib import Path

from quart import Blueprint, jsonify

from core import node_identity

bp = Blueprint("mdns_identity", __name__)


def _load_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_path.read_text().strip()
    except OSError:
        return "0.0.0"


_VERSION = _load_version()


@bp.route("/api/mdns/identity", methods=["GET"])
async def identity():
    from core.llm_router.state import get_catalog
    from core.mdns.address_utils import _pick_lan_ip, _rewrite_host_to_lan

    cat = get_catalog()
    yu_hailo = cat.get_backend("hailo-local") is not None
    hailo_ollama_backend = cat.get_backend("hailo-ollama-local")

    capabilities: list[str] = []
    if yu_hailo:
        capabilities.append("hailo")

    response: dict = {
        "product": "yu_ai_manager",
        "node_id": node_identity.get_node_id(),
        "version": _VERSION,
        "capabilities": capabilities,
    }

    if hailo_ollama_backend is not None and hailo_ollama_backend.base_url:
        lan_ip = _pick_lan_ip()
        if lan_ip:
            rewritten = _rewrite_host_to_lan(
                hailo_ollama_backend.base_url, lan_ip
            )
            if rewritten:
                response["hailo_ollama_url"] = rewritten

    return jsonify(**response)


@bp.route("/api/mdns/peers", methods=["GET"])
async def peers():
    """Debug: expose the live core.mdns MdnsService peer list + status.

    Unauthenticated reads are intentional for diagnostics; the data it
    exposes (node_id, hostname, LAN addresses, TXT capabilities) is the
    same data already broadcast on the LAN via _yu-ai._tcp.local. so it
    carries no additional disclosure. Do NOT add auth-gated info here.
    """
    import core.web.runtime_mdns as rs
    svc = getattr(rs, "_MDNS_SERVICE", None)
    if svc is None:
        return jsonify(
            running=False,
            reason="mdns subsystem not initialised (disabled or init failed)",
            peers=[],
        )
    try:
        status = getattr(svc, "status", None)
    except Exception as exc:  # pragma: no cover - defensive
        status = f"status-error:{exc}"
    try:
        peer_list = svc.list_peers()
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify(running=True, status=str(status), peers=[], error=str(exc))

    def _peer_to_dict(p) -> dict:
        return {
            "node_id": getattr(p, "node_id", None),
            "hostname": getattr(p, "hostname", None),
            "version": getattr(p, "version", None),
            "llm_base_url": getattr(p, "llm_base_url", None),
            "llm_provider": getattr(p, "llm_provider", None),
            "capabilities": list(getattr(p, "capabilities", ()) or ()),
            "web_port": getattr(p, "web_port", None),
            "addresses": list(getattr(p, "addresses", ()) or ()),
            "hailo_ollama_url": getattr(p, "hailo_ollama_url", None),
        }

    response = {
        "running": True,
        "status": str(status),
        "self_node_id": node_identity.get_node_id(),
        "peers": [_peer_to_dict(p) for p in peer_list],
    }
    # Debug-only field. trusted IP リストは本質的に "攻撃対象リスト" なので、
    # unauthenticated エンドポイントにデフォルト露出しない。開発時のみ
    # TAGDB_DEBUG_TRUSTED_PEERS=1 で起動して確認する (spec §5.4)。
    import os
    import time
    if os.environ.get("TAGDB_DEBUG_TRUSTED_PEERS", "").lower() in (
        "1", "true", "yes"
    ):
        from core.web.trusted_peer_registry import get_registry
        response["trusted_ips"] = get_registry().list_all()

        # Bridge state is useful to diagnose why a peer was (or was not)
        # trust-registered. Exposes managed aliases, config-aliased set,
        # and cooldown deadlines relative to monotonic now.
        bridge = getattr(rs, "_MDNS_BRIDGE", None)
        if bridge is not None:
            now = time.monotonic()
            cooldown_ages = {
                nid[:8]: round(deadline - now, 1)
                for nid, deadline in getattr(bridge, "_cooldown", {}).items()
            }
            response["bridge"] = {
                "managed_aliases": sorted(
                    getattr(bridge, "_managed_aliases", set())
                ),
                "config_aliases": sorted(
                    getattr(bridge, "_config_aliases", set())
                ),
                "cooldown_seconds_remaining": cooldown_ages,
            }
    return jsonify(**response)
