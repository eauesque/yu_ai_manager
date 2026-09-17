"""LLM backend callers for translation.

Resolves the appropriate LLM server from the registry and dispatches
translation prompts to Ollama, OpenAI-compatible, Claude, or Hailo backends.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def resolve_translation_server(
    server_id: str | None,
) -> tuple[str, dict, str, str | None]:
    """Resolve translation server from the registry."""
    from core.analysis_api.server_registry import (
        get_all_servers,
        resolve_active_server,
    )
    from core.configuration.api import load_config_json

    config = load_config_json(None)

    if server_id:
        engine_type, kwargs, err = resolve_active_server(config, server_id=server_id)
        if err:
            return "", {}, "", err
        return engine_type, kwargs, server_id, None

    # Use server with high translate score or active server
    engine_type, kwargs, err = resolve_active_server(config)
    if err:
        return "", {}, "", err

    # Determine engine name
    servers = get_all_servers(config)
    name = "unknown"
    active_id = config.get("ai_servers_active", "")
    for srv in servers:
        if srv.id == active_id:
            name = srv.name
            break
    if name == "unknown" and servers:
        name = servers[0].name

    return engine_type, kwargs, name, None


def call_llm(engine_type: str, kwargs: dict, prompt: str) -> str:
    """Dispatch a text prompt to the appropriate LLM backend.

    Uses direct API calls rather than the AnalysisEngine interface,
    since translation only requires text I/O (no vision).
    """
    if engine_type == "ollama":
        return _call_ollama(kwargs, prompt)
    elif engine_type in ("openai", "openai_compat"):
        return _call_openai_compat(kwargs, prompt)
    elif engine_type == "claude_api":
        return _call_claude(kwargs, prompt)
    elif engine_type == "hailo_vlm":
        # Hailo is registered as VLM but uses LLM for text translation
        return _call_hailo_llm(kwargs, prompt)
    else:
        raise RuntimeError(f"Unsupported engine type for translation: {engine_type}")


def _call_ollama(kwargs: dict, prompt: str) -> str:
    """Generate text via Ollama /api/chat endpoint (VLM-model compatible)."""
    import urllib.request

    base_url = kwargs.get("base_url", "http://localhost:11434")
    model = kwargs.get("model", "")

    url = f"{base_url}/api/chat"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "YU-AI-Manager"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    msg = data.get("message", {})
    return msg.get("content", "").strip()


def _call_openai_compat(kwargs: dict, prompt: str) -> str:
    """Generate text via OpenAI-compatible chat/completions API."""
    import urllib.request

    base_url = kwargs.get("base_url", "https://api.openai.com")
    api_key = kwargs.get("api_key", "")
    model = kwargs.get("model", "gpt-4o-mini")

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "YU-AI-Manager",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "").strip()
    return ""


def _call_claude(kwargs: dict, prompt: str) -> str:
    """Generate text via Claude Messages API."""
    import urllib.request

    api_key = kwargs.get("api_key", "")
    model = kwargs.get("model", "claude-sonnet-4-6-20250514")

    url = "https://api.anthropic.com/v1/messages"
    body = json.dumps({
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "YU-AI-Manager",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    content = data.get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"].strip()
    return ""


def _call_hailo_llm(kwargs: dict, prompt: str) -> str:
    """Generate text via Hailo-10H NPU local inference."""
    try:
        import importlib.util
        from pathlib import Path
        # Load from the Hailo GenAI extension module by file path.
        _spec = importlib.util.spec_from_file_location(
            "hailo_genai_llm_inference",
            Path(__file__).resolve().parents[2] / "builtin_hailo_genai" / "core_impl" / "llm_inference.py")
        _llm_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_llm_mod)
        get_llm = _llm_mod.get_llm
    except ImportError as exc:
        raise RuntimeError(
            "Hailo LLM not available. "
            "builtin-hailo-genai extension is required."
        ) from exc

    model_name = kwargs.get("llm_model", "qwen2.5-1.5b-chat")
    llm = get_llm(model_name)
    llm.clear_context()

    messages = [
        {"role": "system", "content": "You are a translator. Translate accurately and naturally."},
        {"role": "user", "content": prompt},
    ]
    result = llm.generate_all(
        messages,
        temperature=0.3,
        max_generated_tokens=1024,
    )
    return result.strip()
