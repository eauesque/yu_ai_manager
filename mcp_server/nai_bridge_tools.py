"""MCP tools for NovelAI Bridge — generate images via NovelAI API."""

import json

from mcp.server.fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def register_nai_bridge_tools(mcp: FastMCP, client):
    """Register NovelAI Bridge MCP tools."""

    @mcp.tool()
    def nai_test_connection() -> str:
        """Test connection to NovelAI API.

        Returns connection status and account info.
        """
        return _json(client.post("/ext/nai-bridge/api/test-connection", {}))

    @mcp.tool()
    def nai_get_anlas() -> str:
        """Get current Anlas balance from NovelAI account."""
        return _json(client.get("/ext/nai-bridge/api/anlas"))

    @mcp.tool()
    def nai_list_models() -> str:
        """List available NovelAI image generation models."""
        return _json(client.get("/ext/nai-bridge/api/models"))

    @mcp.tool()
    def nai_list_samplers() -> str:
        """List available samplers for NovelAI image generation."""
        return _json(client.get("/ext/nai-bridge/api/samplers"))

    @mcp.tool()
    def nai_list_noise_schedules() -> str:
        """List available noise schedules for NovelAI image generation."""
        return _json(client.get("/ext/nai-bridge/api/noise-schedules"))

    @mcp.tool()
    def nai_generate(
        prompt: str,
        negative_prompt: str = "",
        width: int = 832,
        height: int = 1216,
        steps: int = 28,
        sampler: str = "",
        noise_schedule: str = "",
        seed: int = -1,
        model: str = "",
        cfg_scale: float = 5.0,
    ) -> str:
        """Generate an image using NovelAI.

        The image is auto-saved if configured in bridge settings.

        Args:
            prompt: Positive prompt text (required)
            negative_prompt: Negative prompt text
            width: Image width in pixels (default 832)
            height: Image height in pixels (default 1216)
            steps: Sampling steps (1-50, default 28)
            sampler: Sampler name (empty = use default)
            noise_schedule: Noise schedule (empty = use default)
            seed: Seed value (-1 for random)
            model: Model name (empty = use default)
            cfg_scale: CFG scale (default 5.0)
        """
        if not prompt.strip():
            return _err("prompt is required")

        body = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "seed": seed,
            "scale": cfg_scale,  # backend key is "scale"; tool param is cfg_scale for UX clarity
        }
        if sampler:
            body["sampler"] = sampler
        if noise_schedule:
            body["noise_schedule"] = noise_schedule
        if model:
            body["model"] = model

        resp = client.post("/ext/nai-bridge/api/generate", body)
        # Strip base64 image data from MCP response (too large)
        if isinstance(resp, dict) and "images" in resp:
            for img in resp.get("images", []):
                if isinstance(img, dict) and "base64" in img:
                    img["base64"] = f"(base64, {len(img['base64'])} chars)"
        return _json(resp)

    @mcp.tool()
    def nai_get_config() -> str:
        """Get NovelAI Bridge configuration.

        Returns api_token mask, save_folder, auto_save, auto_import, etc.
        """
        return _json(client.get("/ext/nai-bridge/api/config"))

    @mcp.tool()
    def nai_save_config(
        api_token: str = "",
        save_folder: str = "",
        auto_save: bool | None = None,
        auto_import: bool | None = None,
        auto_send: bool | None = None,
        default_model: str = "",
        default_sampler: str = "",
        default_noise_schedule: str = "",
        save_naming: str = "",
        default_image_format: str = "",
        cache_max_size_mb: int = 0,
    ) -> str:
        """Update NovelAI Bridge configuration.

        Only provided (non-empty / non-None) fields are updated.

        Args:
            api_token: NovelAI API token (starts with pst-)
            save_folder: Directory to save generated images
            auto_save: Auto-save generated images to save_folder
            auto_import: Auto-import saved images to database
            auto_send: Auto-send to NAI on prompt submit
            default_model: Default model name (use nai_list_models for valid values)
            default_sampler: Default sampler (use nai_list_samplers for valid values)
            default_noise_schedule: Default noise schedule (use nai_list_noise_schedules)
            save_naming: Folder naming scheme (e.g. daily_folder)
            default_image_format: Image format (png / webp / jpg)
            cache_max_size_mb: Vibe cache max size in MB (0 = no change)
        """
        body: dict = {}
        if api_token:
            body["api_token"] = api_token
        if save_folder:
            body["save_folder"] = save_folder
        if default_model:
            body["default_model"] = default_model
        if default_sampler:
            body["default_sampler"] = default_sampler
        if default_noise_schedule:
            body["default_noise_schedule"] = default_noise_schedule
        if save_naming:
            body["save_naming"] = save_naming
        if default_image_format:
            body["default_image_format"] = default_image_format
        if cache_max_size_mb > 0:
            body["cache_max_size_mb"] = cache_max_size_mb
        if auto_save is not None:
            body["auto_save"] = auto_save
        if auto_import is not None:
            body["auto_import"] = auto_import
        if auto_send is not None:
            body["auto_send"] = auto_send
        if not body:
            return _err("No config fields provided")
        return _json(client.post("/ext/nai-bridge/api/config", body))

    @mcp.tool()
    def nai_save_batch(
        images: list[str],
        seed: int = -1,
        folder: str = "",
        image_format: str = "png",
    ) -> str:
        """Batch-save pre-generated NAI images (e.g. from Sweep deferred-save).

        Each image must be a base64-encoded string. Returns saved file paths
        and file_ids for deep-linking into the Sweep view.

        Args:
            images: List of base64-encoded image strings
            seed: Seed used for generation (-1 if unknown)
            folder: Override save folder (empty = use bridge default)
            image_format: Image format — png, webp, or jpg (default png)
        """
        if not images:
            return _err("images list is required")
        body: dict = {"images": images, "seed": seed, "image_format": image_format}
        if folder:
            body["folder"] = folder
        return _json(client.post("/ext/nai-bridge/api/save-batch", body))
