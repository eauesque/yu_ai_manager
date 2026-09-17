"""MCP tools for the mesh inference disable matrix.

Thin wrappers over /api/mesh-inference/*. One safety guard: the MCP toggle
tool refuses to disable the local peer, forcing an operator to use the
WebUI for that destructive action. This prevents a future LLM orchestrator
from accidentally turning off its own inference capabilities.
"""
from __future__ import annotations

from .llm_tools_common import as_error, as_json


def register_mesh_inference_toggle_tools(mcp, client):
    @mcp.tool()
    def mesh_inference_state() -> str:
        """Return the full mesh inference matrix (peers x inference types)."""
        return as_json(client.get("/api/mesh-inference/state"))

    @mcp.tool()
    def mesh_inference_toggle(
        peer_id: str,
        inference_type: str,
        disabled: bool,
    ) -> str:
        """Enable or disable a single (peer, inference_type) pair.

        Args:
            peer_id: Peer identifier (see mesh_inference_state).
            inference_type: One of tagger, clip, yolo, whisper.
            disabled: True to disable, False to re-enable.

        Safety: MCP agents cannot disable the LOCAL peer through this tool.
        Use the WebUI /mesh-inference for that.
        """
        if not peer_id:
            return as_error("peer_id is required")
        if disabled:
            # Fetch current state to find is_local flag
            state = client.get("/api/mesh-inference/state")
            if isinstance(state, dict):
                peers = state.get("peers", [])
                for p in peers:
                    if p.get("peer_id") == peer_id and p.get("is_local"):
                        return as_error(
                            f"refusing to disable local peer {peer_id!r} "
                            "via MCP; use the WebUI instead"
                        )
        body = {
            "peer_id": peer_id,
            "inference_type": inference_type,
            "disabled": bool(disabled),
        }
        return as_json(client.post("/api/mesh-inference/toggle", body=body))

    @mcp.tool()
    def mesh_inference_bulk(
        action: str,
        inference_type: str = "",
    ) -> str:
        """Run a bulk matrix operation.

        Args:
            action: disable_all_remote | enable_all | local_only
            inference_type: required for disable_all_remote / enable_all

        Safety: local_only is allowed because it does not disable the local
        peer itself; it only disables all remote peers. disable_all_remote
        and enable_all are allowed unconditionally.
        """
        if not action:
            return as_error("action is required")
        body: dict = {"action": action}
        if inference_type:
            body["inference_type"] = inference_type
        return as_json(client.post("/api/mesh-inference/bulk", body=body))
