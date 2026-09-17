"""Generation tools for SD Bridge."""

from mcp.server.fastmcp import FastMCP

from .sd_bridge_tools_common import as_error, as_json, strip_base64_images


def register_sd_bridge_generate_tools(mcp: FastMCP, client):
    """Register SD Bridge generation tools."""

    @mcp.tool()
    def sd_generate(
        prompt: str,
        negative_prompt: str = "",
        steps: int = 28,
        sampler: str = "Euler a",
        cfg_scale: float = 7.0,
        width: int = 512,
        height: int = 768,
        seed: int = -1,
        expand_wildcards: bool = False,
    ) -> str:
        """Generate an image using SD WebUI (txt2img).

        The image is auto-saved if configured in bridge settings.

        Args:
            prompt: Positive prompt text (required)
            negative_prompt: Negative prompt text
            steps: Sampling steps (1-150, default 28)
            sampler: Sampler name (e.g. 'Euler a', 'DPM++ 2M Karras')
            cfg_scale: CFG scale (1-30, default 7.0)
            width: Image width in pixels (64-2048, default 512)
            height: Image height in pixels (64-2048, default 768)
            seed: Seed value (-1 for random)
            expand_wildcards: Expand __wildcard__ and {a|b|c} syntax
        """
        if not prompt.strip():
            return as_error("prompt is required")
        if steps < 1 or steps > 150:
            return as_error(f"steps must be 1-150, got {steps}")
        if width < 64 or width > 2048:
            return as_error(f"width must be 64-2048, got {width}")
        if height < 64 or height > 2048:
            return as_error(f"height must be 64-2048, got {height}")
        body = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "sampler_name": sampler,
            "cfg_scale": cfg_scale,
            "width": width,
            "height": height,
            "seed": seed,
            "expand_wildcards": expand_wildcards,
        }
        return as_json(strip_base64_images(client.post("/ext/sd-webui/api/generate", body)))
