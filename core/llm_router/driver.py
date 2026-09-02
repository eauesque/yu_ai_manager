"""OpenAI-compatible HTTP driver used by the LLM router.

A single Driver instance corresponds to a single backend (Ollama, hailo-ollama,
or any other OpenAI-compatible /v1/chat/completions server).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from core.gateway.timeouts import LLM_TIMEOUTS

from .errors import BackendTimeoutError, BackendUnreachableError, LLMRouterError


class Driver:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        # transport is exposed for tests; in production it stays None and httpx
        # creates a default async transport
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict = {
            "base_url": self.base_url,
            "timeout": httpx.Timeout(
                LLM_TIMEOUTS["total"],
                connect=LLM_TIMEOUTS["connect"],
                read=LLM_TIMEOUTS["first_byte"],
            ),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _discovery_client(self) -> httpx.AsyncClient:
        """Short-timeout client for discovery probes (list_models).

        Uses self.timeout instead of LLM_TIMEOUTS so discovery drivers
        created with timeout=3.0 actually time out in 3 s, not 60 s.
        """
        kwargs: dict = {
            "base_url": self.base_url,
            "timeout": httpx.Timeout(self.timeout),
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def list_models(self) -> list[str]:
        try:
            async with self._discovery_client() as c:
                resp = await c.get("/models", headers=self._headers())
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"list_models timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            raise BackendUnreachableError(f"list_models unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise BackendUnreachableError(
                f"list_models returned {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        return [m["id"] for m in (data.get("data") or []) if "id" in m]

    async def chat(self, openai_body: dict) -> dict:
        # Ensure stream is False for the non-streaming path
        body = dict(openai_body)
        body.pop("stream", None)
        try:
            async with self._client() as c:
                resp = await c.post("/chat/completions", json=body, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"chat timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            raise BackendUnreachableError(f"chat unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise LLMRouterError(
                f"chat returned {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    async def chat_stream(self, openai_body: dict) -> AsyncIterator[dict]:
        body = dict(openai_body)
        body["stream"] = True
        try:
            async with self._client() as c:  # noqa: SIM117
                async with c.stream("POST", "/chat/completions", json=body, headers=self._headers()) as resp:
                    if resp.status_code != 200:
                        text = await resp.aread()
                        raise LLMRouterError(
                            f"chat_stream returned {resp.status_code}: {text[:200]!r}"
                        )
                    _aiter = resp.aiter_lines().__aiter__()
                    saw_done = False
                    saw_finish_reason = False
                    saw_valid_chunk = False
                    # This driver speaks OpenAI-compatible /chat/completions SSE only.
                    # Native Ollama /api/chat uses done:true without [DONE]; that
                    # contract is intentionally not accepted here.
                    malformed_count = 0
                    malformed_streak = 0
                    while True:
                        try:
                            line = await asyncio.wait_for(
                                _aiter.__anext__(),
                                timeout=LLM_TIMEOUTS["inter_token"],
                            )
                        except TimeoutError:
                            raise BackendTimeoutError("inter_token timeout exceeded") from None
                        except StopAsyncIteration:
                            break
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            saw_done = True
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            malformed_count += 1
                            malformed_streak += 1
                            # Two guards cover different backend failure modes:
                            # a mid-stream malformed burst after valid data
                            # aborts at streak 3, while an entirely malformed
                            # stream is rejected at EOF even if the burst is short.
                            if malformed_streak >= 3:
                                raise LLMRouterError("chat_stream received repeated malformed SSE data") from None
                            continue
                        malformed_streak = 0
                        saw_valid_chunk = True
                        choices = chunk.get("choices") if isinstance(chunk, dict) else None
                        if isinstance(choices, list) and any(
                            isinstance(choice, dict) and choice.get("finish_reason") is not None
                            for choice in choices
                        ):
                            saw_finish_reason = True
                        yield chunk
                    if malformed_count and not saw_valid_chunk:
                        raise LLMRouterError("chat_stream received only malformed SSE data")
                    if not saw_done and not saw_finish_reason:
                        raise LLMRouterError("chat_stream ended before completion marker")
        except httpx.TimeoutException as exc:
            raise BackendTimeoutError(f"chat_stream timeout: {exc}") from exc
        except httpx.ConnectError as exc:
            raise BackendUnreachableError(f"chat_stream unreachable: {exc}") from exc
        except httpx.TransportError as exc:
            raise BackendUnreachableError(f"chat_stream transport error: {exc}") from exc
