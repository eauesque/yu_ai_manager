from __future__ import annotations

from collections.abc import AsyncIterator

from core.gateway.errors import BodyTooLargeError


async def iter_body_with_limit(body, limit_bytes: int) -> AsyncIterator[bytes]:
    """Stream Quart request.body chunks, raise BodyTooLargeError when limit exceeded.

    Quart 0.20 request.body is a Body instance with __aiter__/__anext__.
    Do NOT use ASGI receive directly.
    """
    total = 0
    async for chunk in body:
        total += len(chunk)
        if total > limit_bytes:
            raise BodyTooLargeError(limit_bytes)
        if chunk:
            yield chunk
