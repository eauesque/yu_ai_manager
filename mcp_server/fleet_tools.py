"""MCP tools for Fleet Admin (LAN Cowork chief-side management).

Thin wrappers over /ext/lan_cowork/fleet/* chief-session endpoints. All tools
require the local node to be running as a chief; peer-to-peer endpoints that
require a pairing token (X-Peer-Id header) are intentionally NOT exposed here
because the MCP client is an operator, not a paired peer.

Safety guards:
- fleet_update_dispatch / fleet_restart_dispatch refuse to target the local
  peer (defense in depth — the API also rejects self-dispatch).
- fleet_restart_dispatch requires confirm=True to avoid accidental fleet-wide
  restarts from a stray tool call.
"""
from __future__ import annotations

from .llm_tools_common import as_error, as_json

_FLEET = "/ext/lan_cowork/fleet"


def _find_local_peer_id(client) -> str:
    snap = client.get(f"{_FLEET}/peers")
    if isinstance(snap, dict):
        return str(snap.get("responder_peer_id") or "")
    return ""


def register_fleet_tools(mcp, client):
    @mcp.tool()
    def fleet_peers() -> str:
        """Return the Fleet overview snapshot (chief-only).

        Response includes: responder_peer_id, roles_index (role → [peer_id]),
        and peers[] with peer_id, name, roles, machine info (CPU/RAM/GPU/disk/
        git/uptime), last_fetched_at, last_heartbeat_at, reachable, last_error.

        Unpaired peers are filtered out — only peers that have successfully
        authenticated at least once (or are experiencing transient failures)
        appear here.
        """
        return as_json(client.get(f"{_FLEET}/peers"))

    @mcp.tool()
    def fleet_peer_allowlist_status(peer_id: str) -> str:
        """Check whether the local chief is on a target peer's allowlists.

        Calls the target peer's /fleet/allowlists/check over the pairing
        channel. Returns {in_allowlists: [categories...]} or an error.

        Args:
            peer_id: Target peer's peer_id (from fleet_peers).
        """
        if not peer_id:
            return as_error("peer_id is required")
        return as_json(client.get(
            f"{_FLEET}/peer-allowlist-status",
            params={"peer_id": peer_id},
        ))

    @mcp.tool()
    def fleet_peer_grant(peer_id: str, categories: list[str] | None = None) -> str:
        """Ask a target peer to grant the local chief access to its allowlists.

        Args:
            peer_id: Target peer's peer_id.
            categories: List of categories to grant. Valid entries are
                "log_stream" and "update". Defaults to both if omitted.
        """
        if not peer_id:
            return as_error("peer_id is required")
        cats = categories or ["log_stream", "update"]
        return as_json(client.post(
            f"{_FLEET}/peer-grant",
            body={"peer_id": peer_id, "categories": cats},
        ))

    @mcp.tool()
    def fleet_peer_revoke(peer_id: str, categories: list[str] | None = None) -> str:
        """Ask a target peer to revoke the local chief from its allowlists.

        Args:
            peer_id: Target peer's peer_id.
            categories: List of categories to revoke. Defaults to
                ["log_stream", "update"] if omitted.
        """
        if not peer_id:
            return as_error("peer_id is required")
        cats = categories or ["log_stream", "update"]
        return as_json(client.post(
            f"{_FLEET}/peer-revoke",
            body={"peer_id": peer_id, "categories": cats},
        ))

    @mcp.tool()
    def fleet_update_dispatch(
        peer_ids: list[str],
        source: str = "origin",
        branch: str = "main",
    ) -> str:
        """Dispatch a git-pull+restart update to selected peers sequentially.

        Returns {dispatch_id, peer_count}. Poll with fleet_update_dispatch_status
        to track progress.

        Args:
            peer_ids: Target peer IDs (chief cannot dispatch to itself).
            source: "origin" (git pull) or "local:<path>" (rsync from local path).
            branch: Branch name. Must be in fleet.allowed_branches.

        Safety: The local peer_id is stripped from peer_ids before dispatch.
        """
        if not peer_ids:
            return as_error("peer_ids is required")
        local_id = _find_local_peer_id(client)
        filtered = [p for p in peer_ids if p and p != local_id]
        if not filtered:
            return as_error(
                "after filtering the local peer, no peers remain — "
                "MCP refuses to dispatch an update to the local node"
            )
        return as_json(client.post(
            f"{_FLEET}/update/dispatch",
            body={"peer_ids": filtered, "source": source, "branch": branch},
        ))

    @mcp.tool()
    def fleet_update_dispatch_status(dispatch_id: str) -> str:
        """Return progress/result of a previously-dispatched update.

        Args:
            dispatch_id: ID returned by fleet_update_dispatch.
        """
        if not dispatch_id:
            return as_error("dispatch_id is required")
        return as_json(client.get(
            f"{_FLEET}/update/dispatch/status",
            params={"dispatch_id": dispatch_id},
        ))

    @mcp.tool()
    def fleet_restart_dispatch(peer_ids: list[str], confirm: bool = False) -> str:
        """Restart selected peers in parallel (no git pull).

        Args:
            peer_ids: Target peer IDs (chief cannot restart itself).
            confirm: Must be True. Guards against accidental fleet-wide
                restarts from a stray tool call — the caller must explicitly
                pass confirm=True.

        Safety: The local peer_id is stripped before dispatch. confirm=False
        causes this tool to refuse.
        """
        if not confirm:
            return as_error(
                "refusing to restart peers without confirm=True; "
                "pass confirm=True to proceed"
            )
        if not peer_ids:
            return as_error("peer_ids is required")
        local_id = _find_local_peer_id(client)
        filtered = [p for p in peer_ids if p and p != local_id]
        if not filtered:
            return as_error(
                "after filtering the local peer, no peers remain — "
                "MCP refuses to restart the local node"
            )
        return as_json(client.post(
            f"{_FLEET}/restart/dispatch",
            body={"peer_ids": filtered},
        ))
