"""Connection, listing, and config tools for SD Bridge."""

from mcp.server.fastmcp import FastMCP

from .sd_bridge_tools_common import as_error, as_json


def register_sd_bridge_config_tools(mcp: FastMCP, client):
    """Register SD Bridge info and config tools."""

    @mcp.tool()
    def sd_test_connection() -> str:
        """Test connection to the configured SD WebUI instance.

        Returns connection status and current model name.
        """
        return as_json(client.post("/ext/sd-webui/api/test-connection", {}))

    @mcp.tool()
    def sd_list_samplers() -> str:
        """List available samplers from the connected SD WebUI."""
        return as_json(client.get("/ext/sd-webui/api/samplers"))

    @mcp.tool()
    def sd_list_models() -> str:
        """List available checkpoint models from the connected SD WebUI."""
        return as_json(client.get("/ext/sd-webui/api/models"))

    @mcp.tool()
    def sd_list_loras(q: str = "") -> str:
        """List available LoRAs from the connected SD WebUI.

        Returns LoRA names, aliases, and paths.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        return as_json(client.get(f"/ext/sd-webui/api/loras{f'?q={q}' if q else ''}"))

    @mcp.tool()
    def sd_list_embeddings(q: str = "") -> str:
        """List available embeddings from the connected SD WebUI.

        Returns loaded and skipped embedding names.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        return as_json(client.get(f"/ext/sd-webui/api/embeddings{f'?q={q}' if q else ''}"))

    @mcp.tool()
    def sd_list_scripts() -> str:
        """List available scripts from the connected SD WebUI.

        Returns txt2img and img2img script names.
        """
        return as_json(client.get("/ext/sd-webui/api/scripts"))

    @mcp.tool()
    def sd_list_extensions() -> str:
        """List installed extensions from the connected SD WebUI.

        Returns extension names, enabled status, and versions.
        """
        return as_json(client.get("/ext/sd-webui/api/extensions"))

    @mcp.tool()
    def sd_get_progress() -> str:
        """Get current generation progress from SD WebUI.

        Returns progress percentage, current step, total steps, and ETA.
        """
        return as_json(client.get("/ext/sd-webui/api/progress"))

    @mcp.tool()
    def sd_cancel() -> str:
        """Cancel the current SD WebUI generation."""
        return as_json(client.post("/ext/sd-webui/api/cancel", {}))

    @mcp.tool()
    def sd_get_config() -> str:
        """Get SD WebUI Bridge configuration.

        Returns api_url, auto_send, default_sampler, save_folder, etc.
        """
        return as_json(client.get("/ext/sd-webui/api/config"))

    @mcp.tool()
    def sd_save_config(
        api_url: str = "",
        save_folder: str = "",
        auto_save: bool | None = None,
        auto_import: bool | None = None,
        auto_send: bool | None = None,
        bridge_managed_save: bool | None = None,
        default_sampler: str = "",
        save_naming: str = "",
        default_image_format: str = "",
        max_batch_size: int = 0,
        api_key_enc: str = "",
        gateway_url: str = "",
    ) -> str:
        """Update SD WebUI Bridge configuration.

        Only provided (non-empty/non-None) fields are updated.

        Args:
            api_url: SD WebUI API URL (e.g. 'http://127.0.0.1:7860')
            save_folder: Directory to save generated images
            auto_save: Auto-save generated images to save_folder
            auto_import: Auto-import saved images to database
            auto_send: Auto-send to SD WebUI on prompt submit
            bridge_managed_save: Let bridge handle saving instead of SD WebUI
            default_sampler: Default sampler name (use sd_list_samplers for valid values)
            save_naming: Folder naming scheme (e.g. daily_folder)
            default_image_format: Image format (png / webp / jpg)
            max_batch_size: Maximum batch size (1-64, 0 = no change)
            api_key_enc: SD WebUI API key (plain text; bridge encrypts before saving)
            gateway_url: Gateway URL for LAN Cowork proxy
        """
        body = {}
        if api_url:
            body["api_url"] = api_url
        if save_folder:
            body["save_folder"] = save_folder
        if auto_save is not None:
            body["auto_save"] = auto_save
        if auto_import is not None:
            body["auto_import"] = auto_import
        if auto_send is not None:
            body["auto_send"] = auto_send
        if bridge_managed_save is not None:
            body["bridge_managed_save"] = bridge_managed_save
        if default_sampler:
            body["default_sampler"] = default_sampler
        if save_naming:
            body["save_naming"] = save_naming
        if default_image_format:
            body["default_image_format"] = default_image_format
        if max_batch_size > 0:
            body["max_batch_size"] = max_batch_size
        if api_key_enc:
            body["api_key_enc"] = api_key_enc
        if gateway_url:
            body["gateway_url"] = gateway_url
        if not body:
            return as_error("No config fields provided")
        return as_json(client.post("/ext/sd-webui/api/config", body))

    @mcp.tool()
    def sd_switch_model(model: str) -> str:
        """Switch the active checkpoint model in SD WebUI.

        This reloads the model in SD WebUI — may take several seconds.

        Args:
            model: Checkpoint model name (use sd_list_models for valid values)
        """
        if not model.strip():
            return as_error("model is required")
        return as_json(client.post("/ext/sd-webui/api/models/switch", {"model": model}))

    @mcp.tool()
    def sd_refresh_assets() -> str:
        """Ask SD WebUI to rescan checkpoints, VAEs, and LoRAs on disk.

        Call this after adding new model files to SD WebUI's model directories.
        """
        return as_json(client.post("/ext/sd-webui/api/refresh-assets", {}))

    @mcp.tool()
    def sd_save_batch(
        images: list[str],
        seed: int = -1,
        folder: str = "",
        image_format: str = "png",
    ) -> str:
        """Batch-save pre-generated SD WebUI images (e.g. from Sweep deferred-save).

        Each image must be a base64-encoded string. Returns saved file paths
        and file_ids for deep-linking into the Sweep view.

        Args:
            images: List of base64-encoded image strings
            seed: Seed used for generation (-1 if unknown)
            folder: Override save folder (empty = use bridge default)
            image_format: Image format — png, webp, or jpg (default png)
        """
        if not images:
            return as_error("images list is required")
        body: dict = {"images": images, "seed": seed, "image_format": image_format}
        if folder:
            body["folder"] = folder
        return as_json(client.post("/ext/sd-webui/api/save-batch", body))

    @mcp.tool()
    def sd_list_upscalers() -> str:
        """List available SD WebUI upscalers."""
        return as_json(client.get("/ext/sd-webui/api/upscalers"))

    @mcp.tool()
    def sd_get_script_info() -> str:
        """Get detailed script information from SD WebUI."""
        return as_json(client.get("/ext/sd-webui/api/script-info"))
