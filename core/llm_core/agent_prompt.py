"""Prompt-based agent loop helpers for small models."""

from __future__ import annotations

import json
import logging
import re

from .agent_defs import AgentResult, LocalAPIExecutor
from .client import LLMClient

logger = logging.getLogger("core.llm_core.agent")

_TOOL_CALL_RE = re.compile(
    r"(?:<tool_call>\s*)?"
    r"(\{[^{}]*\"name\"\s*:"
    r"[^{}]*\"arguments\"\s*:"
    r"[^{}]*\{[^{}]*\}[^{}]*\})"
    r"(?:\s*</tool_call>)?",
    re.DOTALL,
)
_TOOL_CALL_SIMPLE_RE = re.compile(
    r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^}]*\})\s*\}',
    re.DOTALL,
)


def build_tool_system_prompt(tools: list[dict], user_system_prompt: str = "") -> str:
    """Build a system prompt with tool definitions for prompt-based tool calling."""
    tool_lines: list[str] = []
    for tool in tools:
        fn = tool.get("function", tool)
        props = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])
        if props:
            args_parts = []
            for name, info in props.items():
                marker = " (required)" if name in required else ""
                args_parts.append(
                    f"    {name}: {info.get('type', 'string')} — {info.get('description', '')}{marker}"
                )
            args_str = "\n".join(args_parts)
            tool_lines.append(f"- {fn['name']}: {fn.get('description', '')}\n  Arguments:\n{args_str}")
        else:
            tool_lines.append(f"- {fn['name']}: {fn.get('description', '')}. No arguments.")

    base = user_system_prompt.strip()
    if base:
        base += "\n\n"
    tools_block = "\n".join(tool_lines)
    return (
        f"{base}"
        f"You have tools. To call a tool, respond with ONLY a JSON object:\n"
        f'{{"name": "TOOL_NAME", "arguments": {{}}}}\n\n'
        f"If you do NOT need a tool, respond in natural language.\n\n"
        f"Tools:\n{tools_block}"
    )


def parse_tool_call(text: str) -> dict | None:
    """Extract a tool call JSON from model output when present."""
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "name" in obj:
            args = obj.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            return {"name": obj["name"], "arguments": args}
    except (json.JSONDecodeError, ValueError):
        pass

    match = _TOOL_CALL_RE.search(text)
    if match:
        try:
            obj = json.loads(match.group(1))
            args = obj.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            return {"name": obj["name"], "arguments": args}
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    match = _TOOL_CALL_SIMPLE_RE.search(text)
    if match:
        try:
            return {"name": match.group(1), "arguments": json.loads(match.group(2))}
        except (json.JSONDecodeError, ValueError):
            pass
    return None


async def run_agent_prompt_based(
    client: LLMClient,
    user_message: str,
    tools: list[dict],
    *,
    system_prompt: str = "",
    max_tokens: int = 512,
    temperature: float = 0.1,
    max_rounds: int = 8,
    tool_executor=None,
    clear_context_url: str = "",
) -> AgentResult:
    """Prompt-based agent loop for small LLMs without OpenAI tool calls."""
    import httpx

    if tool_executor is None:
        tool_executor = LocalAPIExecutor()

    if clear_context_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                await http.post(clear_context_url, headers={"X-Requested-With": "XMLHttpRequest"})
        except Exception as exc:
            logger.warning("Failed to clear LLM context: %s", exc)

    messages = [
        {"role": "system", "content": build_tool_system_prompt(tools, system_prompt)},
        {"role": "user", "content": user_message},
    ]
    steps: list[dict] = []

    for round_num in range(max_rounds):
        resp = await client.chat(messages, max_tokens=max_tokens, temperature=temperature)
        content = (resp.content or "").strip()
        if not content:
            return AgentResult("[Empty response from LLM]", resp.model, steps, round_num + 1)

        tool_call = parse_tool_call(content)
        if tool_call is None:
            return AgentResult(content, resp.model, steps, round_num + 1)

        tool_name = tool_call["name"]
        tool_args = tool_call["arguments"]
        logger.info("  [AGENT-PB] tool_call: %s(%s)", tool_name, json.dumps(tool_args, ensure_ascii=False)[:80])
        try:
            result = await tool_executor.execute(tool_name, tool_args)
            result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as exc:
            logger.warning("  [AGENT-PB] tool error: %s — %s", tool_name, exc)
            result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)

        if len(result_str) > 1500:
            result_str = result_str[:1500] + "...(truncated)"

        steps.append({"tool": tool_name, "arguments": tool_args, "result_preview": result_str[:200]})
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": f"Tool result: {result_str}\n\nAnswer the original question using this data."})

    logger.warning("  [AGENT-PB] Max rounds (%d) reached", max_rounds)
    return AgentResult("[Agent reached maximum tool call rounds]", client.model, steps, max_rounds)
