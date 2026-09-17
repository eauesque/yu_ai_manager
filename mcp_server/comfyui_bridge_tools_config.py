"""Connection, listing, and config tools for ComfyUI Bridge."""

from mcp.server.fastmcp import FastMCP

from .comfyui_bridge_tools_common import as_error, as_json


def register_comfyui_bridge_config_tools(mcp: FastMCP, client):
    """Register ComfyUI Bridge info and config tools."""

    @mcp.tool()
    def comfyui_test_connection() -> str:
        """Test connection to the configured ComfyUI instance.

        Returns connection status, ComfyUI version, device info, and VRAM.
        """
        return as_json(client.post("/ext/comfyui-bridge/api/test-connection", {}))

    @mcp.tool()
    def comfyui_list_samplers() -> str:
        """List available samplers from the connected ComfyUI."""
        return as_json(client.get("/ext/comfyui-bridge/api/samplers"))

    @mcp.tool()
    def comfyui_list_schedulers() -> str:
        """List available schedulers from the connected ComfyUI."""
        return as_json(client.get("/ext/comfyui-bridge/api/schedulers"))

    @mcp.tool()
    def comfyui_list_models() -> str:
        """List available checkpoint models (CheckpointLoaderSimple) from the connected ComfyUI."""
        return as_json(client.get("/ext/comfyui-bridge/api/models"))

    @mcp.tool()
    def comfyui_list_diffusion_models() -> str:
        """List available diffusion models (UNETLoader / unet_name) from the connected ComfyUI.

        Use this instead of comfyui_list_models when the workflow uses a separate
        UNETLoader node (e.g. Flux, WAN, SD3, or other diffuser-style workflows).
        """
        return as_json(client.get("/ext/comfyui-bridge/api/diffusion-models"))

    @mcp.tool()
    def comfyui_list_text_encoders(q: str = "") -> str:
        """List available text encoder models (CLIPLoader / clip_name) from the connected ComfyUI.

        Used in Flux, SD3, and other diffuser-style workflows that load CLIP separately.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/text-encoders{params}"))

    @mcp.tool()
    def comfyui_list_clip_types() -> str:
        """List available CLIP types from the connected ComfyUI (e.g. stable_diffusion, flux, etc.)."""
        return as_json(client.get("/ext/comfyui-bridge/api/clip-types"))

    @mcp.tool()
    def comfyui_list_weight_dtypes() -> str:
        """List available weight dtype options for UNETLoader from the connected ComfyUI.

        Returns options like default, fp8_e4m3fn, fp16, bf16, fp32, etc.
        """
        return as_json(client.get("/ext/comfyui-bridge/api/weight-dtypes"))

    @mcp.tool()
    def comfyui_list_controlnets(q: str = "") -> str:
        """List available ControlNet models from the connected ComfyUI.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/controlnets{params}"))

    @mcp.tool()
    def comfyui_list_upscale_models(q: str = "") -> str:
        """List available upscale models from the connected ComfyUI.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/upscale-models{params}"))

    @mcp.tool()
    def comfyui_discovery_models(model_type: str, q: str = "") -> str:
        """Generic model discovery — list models for any ComfyUI loader type.

        Args:
            model_type: Loader type key. One of: checkpoints, diffusion_models,
                text_encoders, controlnet, upscale_models, loras, vae, clip,
                clip_vision, hypernetworks, style_models, unet, gligen
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"type={model_type}"
        if q:
            params += f"&q={q}"
        return as_json(client.get(f"/ext/comfyui-bridge/api/discovery/models?{params}"))

    @mcp.tool()
    def comfyui_refresh_assets() -> str:
        """Re-query ComfyUI's loader nodes to pick up newly-added checkpoints, LoRAs, VAEs, etc.

        Call this after adding new model files to ComfyUI's model directories.
        """
        return as_json(client.post("/ext/comfyui-bridge/api/refresh-assets", {}))

    @mcp.tool()
    def comfyui_list_loras(q: str = "") -> str:
        """List available LoRAs from the connected ComfyUI.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/loras{params}"))

    @mcp.tool()
    def comfyui_list_embeddings(q: str = "") -> str:
        """List available embeddings from the connected ComfyUI.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/embeddings{params}"))

    @mcp.tool()
    def comfyui_list_custom_nodes(q: str = "") -> str:
        """List available custom nodes from the connected ComfyUI.

        Returns node names, categories, and descriptions.

        Args:
            q: Optional filter query (case-insensitive substring match)
        """
        params = f"?q={q}" if q else ""
        return as_json(client.get(f"/ext/comfyui-bridge/api/custom-nodes{params}"))

    @mcp.tool()
    def comfyui_get_progress() -> str:
        """Get current generation progress from ComfyUI.

        Returns progress percentage, current step, total steps, and status.
        """
        return as_json(client.get("/ext/comfyui-bridge/api/progress"))

    @mcp.tool()
    def comfyui_cancel() -> str:
        """Cancel the current ComfyUI generation."""
        return as_json(client.post("/ext/comfyui-bridge/api/cancel", {}))

    @mcp.tool()
    def comfyui_get_config() -> str:
        """Get ComfyUI Bridge configuration.

        Returns api_url, auto_send, default_sampler, default_scheduler,
        save_folder, auto_save, save_naming, auto_import, etc.
        """
        return as_json(client.get("/ext/comfyui-bridge/api/config"))

    @mcp.tool()
    def comfyui_save_config(
        api_url: str = "",
        save_folder: str = "",
        auto_save: bool | None = None,
        auto_import: bool | None = None,
        default_sampler: str = "",
        default_scheduler: str = "",
    ) -> str:
        """Update ComfyUI Bridge configuration.

        Only provided (non-empty/non-None) fields are updated.

        Args:
            api_url: ComfyUI API URL (e.g. 'http://127.0.0.1:8188')
            save_folder: Directory to save generated images
            auto_save: Auto-save generated images to save_folder
            auto_import: Auto-import saved images to database
            default_sampler: Default sampler name (e.g. 'euler', 'dpmpp_2m')
            default_scheduler: Default scheduler name (e.g. 'normal', 'karras')
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
        if default_sampler:
            body["default_sampler"] = default_sampler
        if default_scheduler:
            body["default_scheduler"] = default_scheduler
        if not body:
            return as_error("No config fields provided")
        return as_json(client.post("/ext/comfyui-bridge/api/config", body))
