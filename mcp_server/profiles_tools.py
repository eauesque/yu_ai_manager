import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_profiles_tools(mcp: FastMCP, client: YuManagerClient):
    @mcp.tool()
    def list_profiles() -> str:
        """List all profiles."""
        return _json(client.get("/api/profiles"))

    @mcp.tool()
    def get_profile(name: str) -> str:
        """Get a profile by name. Args: name: profile name"""
        return _json(client.get(f"/api/profiles/{name}"))

    @mcp.tool()
    def create_profile(name: str, description: str = "") -> str:
        """Create a new profile. Args: name: profile name, description: optional description"""
        return _json(client.post("/api/profiles", {"name": name, "description": description}))

    @mcp.tool()
    def update_profile(name: str, settings: dict) -> str:
        """Update profile settings. Args: name: profile name, settings: settings dict to update"""
        return _json(client.put(f"/api/profiles/{name}", settings))

    @mcp.tool()
    def delete_profile(name: str) -> str:
        """Delete a profile. Args: name: profile name"""
        return _json(client.delete(f"/api/profiles/{name}"))

    @mcp.tool()
    def duplicate_profile(name: str, new_name: str) -> str:
        """Duplicate a profile. Args: name: source profile name, new_name: name for the copy"""
        return _json(client.post(f"/api/profiles/{name}/duplicate", {"new_name": new_name}))

    @mcp.tool()
    def rename_profile(name: str, new_name: str) -> str:
        """Rename a profile. Args: name: current profile name, new_name: new name"""
        return _json(client.post(f"/api/profiles/{name}/rename", {"new_name": new_name}))

    @mcp.tool()
    def toggle_profile_favorite(name: str) -> str:
        """Toggle favorite status for a profile. Args: name: profile name"""
        return _json(client.post(f"/api/profiles/{name}/favorite", {}))

    @mcp.tool()
    def export_profile(name: str) -> str:
        """Export a profile. Args: name: profile name"""
        return _json(client.get(f"/api/profiles/{name}/export"))

    @mcp.tool()
    def import_profile_preview(qr_data: str) -> str:
        """Preview a profile import before applying.

        Returns whether the profile exists (mode='existing' with diff)
        or is new (mode='new' with preview data).

        Args:
            qr_data: JSON string of exported profile data
        """
        if not qr_data.strip():
            return _json({"error": "qr_data is required"})
        return _json(client.post("/api/profiles/import-preview", {
            "qr_data": qr_data,
        }))

    @mcp.tool()
    def import_profile(qr_data: str, mode: str = "full") -> str:
        """Import a profile.

        Args:
            qr_data: JSON string of exported profile data
            mode: Import mode - 'full' (overwrite), 'diff' (merge changes only), 'new' (fail if exists)
        """
        if not qr_data.strip():
            return _json({"error": "qr_data is required"})
        if mode not in ("full", "diff", "new"):
            return _json({"error": "mode must be 'full', 'diff', or 'new'"})
        return _json(client.post("/api/profiles/import", {
            "qr_data": qr_data, "mode": mode,
        }))
