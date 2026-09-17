"""Agent loop: LLM + tool calling over local REST API."""

from __future__ import annotations

import json
import logging
from typing import Any

from .agent_defs import (
    AgentResult,
    LocalAPIExecutor,
    ToolExecutor,
    get_all_tools,
    get_default_tools,
)
from .client import LLMClient

__all__ = [
    "AgentResult",
    "LocalAPIExecutor",
    "ToolExecutor",
    "LLMClient",
    "MAX_TOOL_ROUNDS",
    "run_agent",
    "get_all_tools",
    "get_default_tools",
]

logger = logging.getLogger("core.llm_core.agent")

MAX_TOOL_ROUNDS = 8


async def run_agent(
    client: LLMClient,
    messages: list[dict],
    tools: list[dict],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    max_rounds: int = MAX_TOOL_ROUNDS,
    tool_executor: ToolExecutor | None = None,
) -> AgentResult:
    """Run an agent loop with OpenAI-style tool calling."""
    if tool_executor is None:
        tool_executor = LocalAPIExecutor()

    history = list(messages)
    steps: list[dict] = []

    for round_num in range(max_rounds):
        resp = await client.chat(
            history,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools if tools else None,
        )
        if not resp.tool_calls:
            return AgentResult(resp.content, resp.model, steps, round_num + 1)

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        assistant_msg["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {"name": tool_call.name, "arguments": tool_call.arguments},
            }
            for tool_call in resp.tool_calls
        ]
        history.append(assistant_msg)

        for tool_call in resp.tool_calls:
            logger.info("  [AGENT] tool_call: %s(%s)", tool_call.name, tool_call.arguments[:80])
            try:
                result = await tool_executor.execute(tool_call.name, tool_call.parsed_arguments())
                result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
            except Exception as exc:
                logger.warning("  [AGENT] tool error: %s — %s", tool_call.name, exc)
                result_str = json.dumps({"error": str(exc)}, ensure_ascii=False)

            steps.append({
                "tool": tool_call.name,
                "arguments": tool_call.parsed_arguments(),
                "result_preview": result_str[:200],
            })
            history.append({"role": "tool", "tool_call_id": tool_call.id, "content": result_str})

    logger.warning("  [AGENT] Max rounds (%d) reached", max_rounds)
    return AgentResult("[Agent reached maximum tool call rounds]", client.model, steps, max_rounds)
