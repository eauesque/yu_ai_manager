"""Agent/chat helpers for LLM endpoint routes."""

from __future__ import annotations

import logging

from quart import request

from core.infra_core.api_errors import api_error, api_result

logger = logging.getLogger(__name__)


async def run_chat(body: dict):
    category = body.get("category", "").strip()
    messages = body.get("messages", [])
    if not category or not messages:
        return api_error("category and messages are required", 400)

    from core.llm_core import LLMError, get_llm_client

    client = get_llm_client(category)
    if client is None:
        return api_error(f"No LLM endpoint configured for '{category}'", 404)

    try:
        result = await client.chat(
            messages,
            max_tokens=int(body.get("max_tokens", 1024)),
            temperature=float(body.get("temperature", 0.7)),
        )
        return api_result(
            {
                "content": result.content,
                "model": result.model,
                "usage": result.usage,
            }
        )
    except LLMError as exc:
        logger.warning("LLM chat failed for category=%s: %s", category, exc)
        return api_error("LLM request failed", 502)


async def run_agent_request(body: dict):
    category = body.get("category", "").strip()
    message = body.get("message", "").strip()
    if not category or not message:
        return api_error("category and message are required", 400)

    from core.llm_core import LLMError, get_llm_client

    client = get_llm_client(category)
    client = _ensure_hailo_client(category, body, client)
    if client is None:
        return api_error(f"No LLM endpoint configured for '{category}'", 404)

    mode = _resolve_mode(body, client)
    tools, max_rounds = _resolve_agent_tools(body)
    base_url = _resolve_local_base_url()
    auth_headers = {
        header: request.headers[header]
        for header in ("Authorization", "X-Api-Key", "Cookie")
        if header in request.headers
    }
    system_prompt = body.get(
        "system_prompt",
        "You are a helpful assistant. Use the available tools to answer questions about the file database.",
    )

    try:
        result = await _run_agent_mode(
            client,
            message,
            tools,
            mode,
            system_prompt,
            max_rounds,
            body,
            base_url,
            auth_headers,
        )
        return api_result(result.to_dict())
    except LLMError as exc:
        logger.warning("LLM agent failed for category=%s: %s", category, exc)
        return api_error("LLM agent request failed", 502)


def _ensure_hailo_client(category: str, body: dict, client):
    if client is not None or category != "hailo":
        return client

    from core.llm_core.client import LLMClient

    return LLMClient(
        base_url=f"{_resolve_local_base_url()}/ext/hailo-genai/v1",
        model=body.get("model", "qwen2.5-coder-1.5b"),
        timeout=120.0,
        category="hailo",
    )


def _resolve_mode(body: dict, client) -> str:
    mode = body.get("mode", "").strip()
    if not mode and "hailo-genai" in client.base_url:
        return "prompt_based"
    return mode


def _resolve_agent_tools(body: dict):
    from core.llm_core.agent_loop import get_all_tools, get_default_tools

    tools_param = body.get("tools")
    if tools_param == "all":
        tools = get_all_tools()
    elif tools_param:
        tools = tools_param
    else:
        tools = get_default_tools()
    return tools, min(int(body.get("max_rounds", 8)), 8)


def _resolve_local_base_url() -> str:
    return f"http://127.0.0.1:{_resolve_local_port()}"


def _resolve_local_port() -> int:
    from core.services_core.db_state import get_config

    config = get_config() or {}
    server = config.get("server") or {}
    try:
        port = int(server.get("port", 5000))
    except (TypeError, ValueError):
        port = 5000
    return port if 1 <= port <= 65535 else 5000


async def _run_agent_mode(client, message, tools, mode, system_prompt, max_rounds, body, base_url, auth_headers):
    from core.llm_core.agent_loop import LocalAPIExecutor, run_agent
    from core.llm_core.agent_prompt import run_agent_prompt_based

    if mode == "prompt_based":
        clear_url = ""
        if "hailo-genai" in client.base_url:
            clear_url = client.base_url.rsplit("/v1", 1)[0] + "/api/llm/clear-context"
        return await run_agent_prompt_based(
            client,
            message,
            tools,
            system_prompt=system_prompt,
            max_tokens=int(body.get("max_tokens", 512)),
            temperature=float(body.get("temperature", 0.1)),
            max_rounds=max_rounds,
            tool_executor=LocalAPIExecutor(base_url, auth_headers),
            clear_context_url=clear_url,
        )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    return await run_agent(
        client,
        messages,
        tools,
        max_tokens=int(body.get("max_tokens", 1024)),
        temperature=float(body.get("temperature", 0.3)),
        max_rounds=max_rounds,
        tool_executor=LocalAPIExecutor(base_url, auth_headers),
    )


async def get_agent_capabilities():
    from core.llm_core.agent_loop import get_all_tools, get_default_tools

    hailo_available, hailo_models = await _discover_hailo_models()
    read_tools = [tool["function"]["name"] for tool in get_default_tools()]
    write_tools = [
        tool["function"]["name"]
        for tool in get_all_tools()
        if tool["function"]["name"] not in read_tools
    ]
    return api_result(
        {
            "hailo_available": hailo_available,
            "recommended_model": "qwen2.5-coder-1.5b",
            "available_models": hailo_models,
            "usage": {
                "category": "hailo",
                "tools_default": "read-only (search, stats, collections, server info)",
                "tools_all": "read + write (tags, collections, ratings, favorites)",
                "example": {
                    "endpoint": "POST /api/llm/agent",
                    "body": {
                        "category": "hailo",
                        "message": "your task here",
                        "tools": "all",
                        "max_rounds": 5,
                    },
                },
                "mcp_tool": "llm_agent_run(category='hailo', message='...', tools='all')",
            },
            "tools": {"read": read_tools, "write": write_tools},
            "strengths": [
                "Zero API cost — runs entirely on local Hailo-10H NPU",
                "Works offline — no internet required",
                "Fast for structured tool calling — search, tag, rate, organize",
                "Single-step tool calls are highly reliable",
                "Good at: file search, stats lookup, tag operations, collection management, rating",
            ],
            "limitations": [
                "1.5B parameter model — limited reasoning capability",
                "Max ~2-3 tool call rounds are reliable; beyond that quality degrades",
                "Cannot analyze image content (use VLM separately for that)",
                "Poor at: ambiguous instructions, multi-step planning, creative writing",
                "Context window is small — large search results are truncated to 1500 chars",
                "Shares NPU bandwidth with other Hailo models — concurrent CLIP/YOLO/VLM workloads are time-sliced by HailoRT scheduler and may slow each other down",
            ],
            "delegation_guidelines": {
                "delegate_to_hailo": [
                    "Simple file searches by tag (search_files)",
                    "Database statistics queries (get_stats)",
                    "Batch tag operations (set_tags with known file_ids)",
                    "Adding/removing files to/from collections",
                    "Rating files (rate_image)",
                    "Toggling favorites",
                    "Listing collections or scan roots",
                ],
                "keep_in_orchestrator": [
                    "Complex multi-step plans requiring reasoning",
                    "Tasks needing image content understanding",
                    "Ambiguous or open-ended instructions",
                    "Tasks requiring more than 3 tool calls",
                    "Any task requiring external API calls",
                ],
            },
        }
    )


async def _discover_hailo_models():
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(
                f"{_resolve_local_base_url()}/ext/hailo-genai/v1/models",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    model["id"]
                    for model in data.get("data", [])
                    if model.get("owned_by") == "hailo"
                    and model["id"] not in ("whisper-base", "whisper-small", "clip-vit-b-16")
                ]
                return True, models
    except Exception:
        logger.warning("LLM endpoint step failed", exc_info=True)
    return False, []
