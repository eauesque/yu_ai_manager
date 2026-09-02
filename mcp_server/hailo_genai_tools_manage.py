"""General MCP tools for Hailo GenAI extension."""

import json

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .validators import validate_file_id

_PFX = "/ext/hailo-genai"


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def register_hailo_genai_manage_tools(mcp: FastMCP, client: YuManagerClient):
    """Register non-benchmark Hailo GenAI tools on the MCP server."""

    @mcp.tool()
    def hailo_genai_status() -> str:
        """Get runtime state of the Hailo GenAI extension."""
        return _json(client.get(f"{_PFX}/api/runtime"))

    @mcp.tool()
    def hailo_genai_model_status() -> str:
        """Get Hailo GenAI model load state and availability."""
        return _json(client.get(f"{_PFX}/api/model/status"))

    @mcp.tool()
    def hailo_genai_model_download(model_name: str = "") -> str:
        """Download a Hailo GenAI model.

        Args:
            model_name: Model name to download. Empty for default model.
        """
        body = {"model_name": model_name} if model_name else {}
        return _json(client.post(f"{_PFX}/api/model/download", body))

    @mcp.tool()
    def hailo_genai_model_unload() -> str:
        """Unload the currently loaded Hailo GenAI model."""
        return _json(client.post(f"{_PFX}/api/model/unload", {}))

    @mcp.tool()
    def hailo_llm_generate(
        prompt: str = "",
        messages: list | None = None,
        model: str = "",
        max_tokens: int = 256,
        temperature: float = 0.7,
        system_prompt: str = "",
    ) -> str:
        """Generate text using Hailo LLM (single-turn or multi-turn).

        Either `prompt` (single-turn) or `messages` (multi-turn) must be provided.
        `messages` takes priority when both are supplied.

        Args:
            prompt: Single-turn prompt text (mutually exclusive with messages)
            messages: Multi-turn message list, e.g. [{"role": "user", "content": "Hello"}]
            model: LLM model name (empty = server default)
            max_tokens: Maximum tokens to generate (default 256)
            temperature: Sampling temperature 0.0–1.0 (default 0.7)
            system_prompt: System prompt (only used with single-turn prompt)
        """
        body: dict = {
            "max_generated_tokens": max_tokens,
            "temperature": temperature,
        }
        if messages and isinstance(messages, list):
            body["messages"] = messages
        elif prompt and prompt.strip():
            body["prompt"] = prompt.strip()
            if system_prompt:
                body["system_prompt"] = system_prompt
        else:
            return _json({"error": "prompt or messages is required"})
        if model:
            body["model"] = model
        return _json(client.post_sse(f"{_PFX}/api/llm/generate", body))

    @mcp.tool()
    def hailo_llm_clear_context() -> str:
        """Clear the Hailo LLM conversation context."""
        return _json(client.post(f"{_PFX}/api/llm/clear-context", {}))

    @mcp.tool()
    def hailo_vlm_generate(
        file_id: int,
        prompt: str = "Describe this image.",
        model: str = "",
        temperature: float = 0.7,
        system_prompt: str = "",
        max_generated_tokens: int = 256,
    ) -> str:
        """Generate text from an image using Hailo VLM.

        Args:
            file_id: ID of the image file in the database
            prompt: Instruction / question about the image (default "Describe this image.")
            model: VLM model name (empty = server default)
            temperature: Sampling temperature 0.0–1.0 (default 0.7)
            system_prompt: System prompt (default "You are a helpful assistant that analyzes images.")
            max_generated_tokens: Maximum tokens to generate (default 256)
        """
        err = validate_file_id(file_id)
        if err:
            return err
        body: dict = {
            "file_id": file_id,
            "prompt": prompt,
            "temperature": temperature,
            "max_generated_tokens": max_generated_tokens,
        }
        if model:
            body["model"] = model
        if system_prompt:
            body["system_prompt"] = system_prompt
        return _json(client.post_sse(f"{_PFX}/api/vlm/generate", body))

    @mcp.tool()
    def hailo_genai_openai_info() -> str:
        """Get OpenAI-compatible API endpoint information for Hailo GenAI."""
        base = f"{_PFX}/v1"
        return _json({
            "base_url": base,
            "endpoints": {
                "models": f"GET {base}/models",
                "chat_completions": f"POST {base}/chat/completions",
                "audio_transcriptions": f"POST {base}/audio/transcriptions",
                "embeddings": f"POST {base}/embeddings",
            },
            "notes": {
                "auth": "Use YU API Key (sk_...) as Bearer token",
                "vision": "Include base64 image_url in messages for VLM",
                "audio": "Non-WAV files auto-converted via ffmpeg",
                "embeddings": "CLIP ViT-B/16 (512-dim), requires builtin-clip-search",
            },
        })
