from __future__ import annotations


def build_capabilities(models: list[dict]) -> dict:
    return {
        "version": "1",
        "phase": 1,
        "responses_api_subset": {
            "non_stream": False,
            "stream": False,
            "tools_function": False,
            "tools_builtin": False,
            "previous_response_id": "unsupported",
            "reasoning_items": False,
            "background": False,
        },
        "chat_completions": {"stream": True, "tools": True},
        "anthropic_messages": {"stream": True, "tools": True},
        "image_backends": ["sd_webui", "comfyui"],
        "models": models,
    }
