"""MCP tools for ComfyUI model registry management."""

from mcp.server.fastmcp import FastMCP

from .comfyui_bridge_tools_common import as_error, as_json


def register_comfyui_bridge_registry_tools(mcp: FastMCP, client) -> None:
    """Register ComfyUI model registry MCP tools."""

    @mcp.tool()
    def comfyui_list_model_registry() -> str:
        """Get the ComfyUI model registry and available models in one call.

        Returns the merged registry (user entries + built-in entries) along with
        currently available diffusion models, VAEs, and text encoders from ComfyUI.
        Use this to understand which models are registered and which are available,
        then call comfyui_set_model_registry_entry to add or update entries.

        Built-in entries (builtin=true) cannot be deleted but can be overridden by
        creating a user entry with the same id.
        """
        return as_json(client.get("/ext/comfyui-bridge/api/model-registry"))

    @mcp.tool()
    def comfyui_set_model_registry_entry(
        entry_id: str,
        unet_patterns: list[str],
        vae: str = "",
        clip_1: str = "",
        clip_2: str = "",
        clip_type: str = "",
        latent_node: str = "",
        source_url: str = "",
        default_sampler: str = "",
        default_scheduler: str = "",
        default_cfg: float | None = None,
        default_steps: int | None = None,
        notes: str = "",
    ) -> str:
        """Add or update a user model registry entry.

        Registry entries map a model filename pattern to its required VAE,
        CLIP, and clip_type. This allows comfyui_generate to automatically
        select the correct components when a diffusion_model is specified.

        Args:
            entry_id: Unique entry identifier (letters, digits, hyphens, underscores, max 64 chars).
                Use the same id as a built-in entry to override it.
            unet_patterns: List of case-insensitive substring patterns to match against
                the diffusion model filename (e.g. ["wan2.2", "wan2_2"]).
            vae: Substring hint for selecting the VAE model (e.g. "wan2.2_vae").
            clip_1: Substring hint for selecting the primary text encoder (e.g. "umt5_xxl").
            clip_2: Substring hint for secondary text encoder (for dual-CLIP workflows).
            clip_type: CLIPLoader type parameter (e.g. "wan", "flux", "stable_diffusion",
                "sd3", "stable_cascade", "mochi", "ltxv", "cosmos", "hidream", "qwen_image").
            latent_node: ComfyUI node class for empty latent creation (stored, not yet applied).
            source_url: Optional URL for model documentation or download.
            default_sampler: Default sampler name override for this model.
            default_scheduler: Default scheduler name override for this model.
            default_cfg: Default CFG scale override for this model.
            default_steps: Default step count override for this model.
            notes: Free-text notes about the model or its required settings.
        """
        if not entry_id or not entry_id.strip():
            return as_error("entry_id is required")
        if not unet_patterns:
            return as_error("unet_patterns is required (at least one pattern)")

        body: dict = {
            "id": entry_id,
            "unet_patterns": unet_patterns,
        }
        if vae:
            body["vae"] = vae
        if clip_1:
            body["clip_1"] = clip_1
        if clip_2:
            body["clip_2"] = clip_2
        if clip_type:
            body["clip_type"] = clip_type
        if latent_node:
            body["latent_node"] = latent_node
        if source_url:
            body["source_url"] = source_url
        if default_sampler:
            body["default_sampler"] = default_sampler
        if default_scheduler:
            body["default_scheduler"] = default_scheduler
        if default_cfg is not None:
            body["default_cfg"] = default_cfg
        if default_steps is not None:
            body["default_steps"] = default_steps
        if notes:
            body["notes"] = notes

        return as_json(client.post("/ext/comfyui-bridge/api/model-registry", body))

    @mcp.tool()
    def comfyui_delete_model_registry_entry(entry_id: str) -> str:
        """Delete a user model registry entry by id.

        Only user-defined entries can be deleted. Built-in entries cannot be
        deleted, but can be overridden by creating a user entry with the same id.

        To effectively hide a built-in entry: create a user entry with the same id
        and different (or empty) patterns that won't match any model.

        Args:
            entry_id: The entry id to delete (must exist in the user registry).
        """
        if not entry_id or not entry_id.strip():
            return as_error("entry_id is required")
        return as_json(client.delete(f"/ext/comfyui-bridge/api/model-registry/{entry_id}"))
