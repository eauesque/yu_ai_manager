"""Generation tools for ComfyUI Bridge."""

import json

from mcp.server.fastmcp import FastMCP

from .comfyui_bridge_tools_common import as_error, as_json


def _strip_base64_images(response):
    if isinstance(response, dict) and "images" in response:
        for image in response.get("images", []):
            if isinstance(image, dict) and "base64" in image:
                image["base64"] = f"(base64, {len(image['base64'])} chars)"
    return response


def register_comfyui_bridge_generate_tools(mcp: FastMCP, client):
    """Register ComfyUI Bridge generation tools."""

    @mcp.tool()
    def comfyui_generate(
        prompt: str,
        negative_prompt: str = "",
        steps: int = 20,
        sampler_name: str = "euler",
        scheduler: str = "normal",
        cfg: float = 7.0,
        width: int = 512,
        height: int = 768,
        seed: int = -1,
        ckpt_name: str = "",
        expand_wildcards: bool = False,
        image_format: str = "png",
        loras: str = "",
        diffusion_model: str = "",
        text_encoder_1: str = "",
        text_encoder_2: str = "",
        vae_name: str = "",
        clip_type: str = "",
        weight_dtype: str = "",
    ) -> str:
        """Generate an image using ComfyUI (simple mode, txt2img).

        The image is auto-saved if configured in bridge settings.

        Two loader modes are supported:
        - Checkpoint mode (default): specify ckpt_name. Use comfyui_list_models to find names.
        - Separate-load mode (Flux/SD3/Wan/UNET): specify diffusion_model + text_encoder_1 +
          vae_name. Use comfyui_list_diffusion_models, comfyui_list_text_encoders, and
          comfyui_discovery_models to find names. text_encoder_2 is optional (DualCLIPLoader).

        If both ckpt_name and diffusion_model are empty, the backend will report which
        model types are available so you can pick the right mode.

        Args:
            prompt: Positive prompt text (required). May contain `<lora:NAME:WEIGHT>` tokens.
            negative_prompt: Negative prompt text
            steps: Sampling steps (1-150, default 20)
            sampler_name: Sampler name (e.g. 'euler', 'dpmpp_2m', 'euler_ancestral')
            scheduler: Scheduler name (e.g. 'normal', 'karras', 'exponential')
            cfg: CFG scale (1-30, default 7.0)
            width: Image width in pixels (64-2048, default 512)
            height: Image height in pixels (64-2048, default 768)
            seed: Seed value (-1 for random)
            ckpt_name: Checkpoint model name. Mutually exclusive with diffusion_model.
            expand_wildcards: Expand __wildcard__ and {a|b|c} syntax
            image_format: Output format - 'png', 'webp', or 'jpg' (default 'png')
            loras: Optional JSON array string of LoRAs, e.g.
                '[{"name":"style.safetensors","strength_model":0.8,"strength_clip":0.8}]'.
                Alternatively embed `<lora:NAME:WEIGHT>` tokens directly in the prompt.
            diffusion_model: UNETLoader model name (separate-load mode). Mutually exclusive
                with ckpt_name. Use comfyui_list_diffusion_models.
            text_encoder_1: CLIPLoader / DualCLIPLoader clip_name1. Required in separate-load
                mode. Use comfyui_list_text_encoders.
            text_encoder_2: DualCLIPLoader clip_name2 (optional second encoder).
            vae_name: VAELoader model name. Required in separate-load mode.
                Use comfyui_discovery_models with type 'vae'.
            clip_type: CLIPLoader type override (e.g. 'stable_diffusion', 'sdxl',
                'stable_cascade', 'sd3', 'flux', 'mochi', 'ltxv', 'pixart',
                'cosmos', 'lumina2', 'wan', 'hidream', 'chroma', 'ace',
                'qwen_image'). Leave empty to auto-detect.
            weight_dtype: UNETLoader weight dtype override (e.g. 'fp8_e4m3fn', 'fp16').
                Leave empty for 'default'.
        """
        if not prompt.strip():
            return as_error("prompt is required")
        if steps < 1 or steps > 150:
            return as_error(f"steps must be 1-150, got {steps}")
        if width < 64 or width > 2048:
            return as_error(f"width must be 64-2048, got {width}")
        if height < 64 or height > 2048:
            return as_error(f"height must be 64-2048, got {height}")
        if image_format not in ("png", "webp", "jpg"):
            return as_error(f"image_format must be png/webp/jpg, got {image_format}")
        body = {
            "mode": "simple",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "cfg": cfg,
            "width": width,
            "height": height,
            "seed": seed,
            "expand_wildcards": expand_wildcards,
            "image_format": image_format,
        }
        if ckpt_name:
            body["ckpt_name"] = ckpt_name
        if diffusion_model:
            body["diffusion_model"] = diffusion_model
        if text_encoder_1:
            body["text_encoder_1"] = text_encoder_1
        if text_encoder_2:
            body["text_encoder_2"] = text_encoder_2
        if vae_name:
            body["vae_name"] = vae_name
        if clip_type:
            body["clip_type"] = clip_type
        if weight_dtype:
            body["weight_dtype"] = weight_dtype
        if loras:
            try:
                parsed_loras = json.loads(loras)
            except json.JSONDecodeError as e:
                return as_error(f"Invalid loras JSON: {e}")
            if not isinstance(parsed_loras, list):
                return as_error("loras must be a JSON array")
            body["loras"] = parsed_loras
        return as_json(_strip_base64_images(client.post("/ext/comfyui-bridge/api/generate", body)))

    @mcp.tool()
    def comfyui_generate_json(workflow: str) -> str:
        """Generate an image using ComfyUI with a raw JSON workflow.

        For advanced users who need full control over the ComfyUI node graph.

        Args:
            workflow: ComfyUI workflow JSON string (full node graph definition)
        """
        try:
            parsed = json.loads(workflow)
        except json.JSONDecodeError as e:
            return as_error(f"Invalid JSON workflow: {e}")
        return as_json(_strip_base64_images(client.post("/ext/comfyui-bridge/api/generate", {"mode": "json", "workflow": parsed})))

    @mcp.tool()
    def get_workflow_gen_params(file_id: int) -> str:
        """Get generation parameters backup stored in a bridge-generated image.

        Returns the _gen_params JSON (model, steps, seed, LoRAs, etc.) that was
        embedded when the image was generated via ComfyUI Bridge simple mode.
        Pass this JSON directly to an LLM to reconstruct a ComfyUI workflow.

        Args:
            file_id: The file ID from the yu_ai_manager database.

        Returns:
            JSON string with generation parameters, or error message if not found.
        """
        from pathlib import Path

        from core.services_core.db_api import get_readonly_db

        try:
            con = get_readonly_db()
            row = con.execute(
                "SELECT path FROM files WHERE id=? AND is_deleted=0", (file_id,)
            ).fetchone()
            if not row:
                return as_error("File not found")

            file_path = Path(row[0])
            if not file_path.is_file():
                return as_error("File not found on disk")

            from extensions.builtin_comfyui_bridge.core_impl.comfyui_image_workflow import (
                extract_gen_params_from_image,
            )

            gen_params = extract_gen_params_from_image(
                file_path.read_bytes(), file_path.name
            )
            if not gen_params:
                return as_error("No generation params backup found in this image")

            return as_json({
                "gen_params": gen_params,
                "hint": (
                    "This JSON contains the generation parameters used to create "
                    "this image. Pass it directly to an LLM to reconstruct a "
                    "ComfyUI workflow."
                ),
            })
        except Exception as exc:  # noqa: BLE001
            return as_error(f"Error reading gen params: {exc}")
