"""Profile management and active-model tools for WD-Tagger."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .wd_tagger_tools_common import as_json


def register_wd_tagger_profile_tools(mcp: FastMCP, client: YuManagerClient):
    """Register WD-Tagger profile CRUD and active-model tools."""

    @mcp.tool()
    def wd_tagger_list_profiles() -> str:
        """List all WD-Tagger model profiles with their metadata and active model.

        Returns a list of profiles (id, display_name, model_id, threshold, etc.)
        and the currently active model ID.
        """
        return as_json(client.get("/api/wd-tagger/profiles"))

    @mcp.tool()
    def wd_tagger_get_profile(profile_id: str) -> str:
        """Get full details of a WD-Tagger model profile by ID.

        Args:
            profile_id: Profile ID (e.g. 'wd-v1-4-moat-tagger-v2')
        """
        if not profile_id or not profile_id.strip():
            return as_json({"error": "profile_id is required"})
        return as_json(client.get(f"/api/wd-tagger/profiles/{profile_id.strip()}"))

    @mcp.tool()
    def wd_tagger_create_profile(profile: dict) -> str:
        """Create a new WD-Tagger model profile.

        Args:
            profile: Profile definition dict. Required fields:
                - id (str): Unique profile identifier
                - display_name (str): Human-readable name
                - model_id (str): WD-Tagger model ID
                - threshold (float): Tag confidence threshold (0.0–1.0)
            Optional fields:
                - character_threshold (float)
                - exclude_tags (list[str])
                - vlm_endpoint (str)
        """
        return as_json(client.post("/api/wd-tagger/profiles", profile))

    @mcp.tool()
    def wd_tagger_update_profile(profile_id: str, profile: dict) -> str:
        """Update an existing WD-Tagger model profile (partial update).

        Args:
            profile_id: Profile ID to update
            profile: Fields to update (only provided fields are changed)
        """
        if not profile_id or not profile_id.strip():
            return as_json({"error": "profile_id is required"})
        return as_json(client.put(f"/api/wd-tagger/profiles/{profile_id.strip()}", profile))

    @mcp.tool()
    def wd_tagger_delete_profile(profile_id: str) -> str:
        """Delete a WD-Tagger model profile.

        Built-in profiles cannot be deleted.

        Args:
            profile_id: Profile ID to delete
        """
        if not profile_id or not profile_id.strip():
            return as_json({"error": "profile_id is required"})
        return as_json(client.delete(f"/api/wd-tagger/profiles/{profile_id.strip()}"))

    @mcp.tool()
    def wd_tagger_get_active_model() -> str:
        """Get the currently active WD-Tagger model ID and list of available models."""
        return as_json(client.get("/api/wd-tagger/active-model"))

    @mcp.tool()
    def wd_tagger_set_active_model(model_id: str) -> str:
        """Set the active WD-Tagger model.

        Use wd_tagger_list_profiles() or wd_tagger_get_active_model() to discover
        valid model IDs first.

        Args:
            model_id: WD-Tagger model ID to activate, or empty string to clear
        """
        payload: dict = {"model_id": model_id.strip() if model_id and model_id.strip() else None}
        return as_json(client.put("/api/wd-tagger/active-model", payload))
