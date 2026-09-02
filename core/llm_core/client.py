"""Async HTTP client for OpenAI-compatible /v1/chat/completions."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator

import httpx

from .models import (
    ChatResponse,
    LLMConnectionError,
    LLMResponseError,
    StreamChunk,
    ToolCall,
)

logger = logging.getLogger("core.llm_core")


class LLMClient:
    """OpenAI-compatible chat client (async, httpx-based)."""

    __slots__ = ("base_url", "model", "api_key", "timeout", "_category")

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60.0, category: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._category = category

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        # Add CSRF header for local endpoints (same-server extensions)
        if "127.0.0.1" in self.base_url or "localhost" in self.base_url:
            h["X-Requested-With"] = "XMLHttpRequest"
        return h

    async def chat(self, messages: list[dict], *, max_tokens: int = 1024, temperature: float = 0.7, tools: list[dict] | None = None) -> ChatResponse:
        """Send a chat completion request and return the response."""
        url = f"{self.base_url}/chat/completions"
        payload: dict = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": False}
        if tools:
            payload["tools"] = tools
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise LLMConnectionError(str(exc)) from exc

        elapsed_ms = round((time.monotonic() - t0) * 1000)

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            raise LLMResponseError(status_code=resp.status_code, message=f"HTTP {resp.status_code}: {detail}")

        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        usage = data.get("usage")
        model = data.get("model", self.model)

        # Parse tool_calls if present
        raw_tool_calls = msg.get("tool_calls")
        tool_calls = None
        if raw_tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=tc.get("function", {}).get("arguments", "{}"),
                )
                for tc in raw_tool_calls
            ]

        logger.info("LLM [%s] %s → %dms (prompt=%s, completion=%s%s)", self._category or "?", model, elapsed_ms, usage.get("prompt_tokens", "?") if usage else "?", usage.get("completion_tokens", "?") if usage else "?", f", tools={len(tool_calls)}" if tool_calls else "")
        return ChatResponse(content=content, model=model, usage=usage, tool_calls=tool_calls)

    async def chat_stream(self, messages: list[dict[str, str]], *, max_tokens: int = 1024, temperature: float = 0.7) -> AsyncIterator[StreamChunk]:
        """Stream chat completion chunks."""
        url = f"{self.base_url}/chat/completions"
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:  # noqa: SIM117
                async with client.stream("POST", url, json=payload, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        raise LLMResponseError(status_code=resp.status_code, message=f"HTTP {resp.status_code}: {body.decode(errors='replace')}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            return
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            yield StreamChunk(delta=delta.get("content", ""), finish_reason=data["choices"][0].get("finish_reason"))
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise LLMConnectionError(str(exc)) from exc
