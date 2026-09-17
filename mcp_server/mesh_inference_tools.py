"""MCP tools for mesh-based inference management.

Replaces distributed_inference_tools — uses mesh peer discovery
instead of manual server registry.
"""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_mesh_inference_tools(mcp: FastMCP, client: YuManagerClient):
    """Register mesh inference MCP tools."""

    @mcp.tool()
    def mesh_inference_peers() -> str:
        """List all mesh peers with their inference capabilities."""
        from core.mesh_inference import get_router
        router = get_router()
        if router is None:
            return _json({"error": "Mesh not available"})
        # Collect peers with any inference type
        all_peers = [router._local_peer] + router._registry.list_online()
        peers = []
        seen = set()
        for p in all_peers:
            if p.peer_id not in seen and p.inference_types:
                seen.add(p.peer_id)
                peers.append({
                    "peer_id": p.peer_id,
                    "name": p.name,
                    "host": p.api_host,
                    "port": p.api_port,
                    "status": p.status,
                    "inference_types": p.inference_types,
                    "is_local": p.peer_id == router._local_peer.peer_id,
                })
        return _json({"peers": peers})

    @mcp.tool()
    def mesh_inference_health() -> str:
        """Check health of all mesh inference peers."""
        from core.mesh_inference import get_router, has_mesh
        if not has_mesh():
            return _json({"error": "Mesh not available"})
        router = get_router()
        local = router._local_peer
        remote = router._registry.list_online()
        results = []
        for p in [local] + remote:
            results.append({
                "peer_id": p.peer_id,
                "name": p.name,
                "status": p.status,
                "inference_types": p.inference_types,
                "is_local": p.peer_id == local.peer_id,
            })
        return _json({"peers": results})
