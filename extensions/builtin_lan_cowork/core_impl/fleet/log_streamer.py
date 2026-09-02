"""Fleet log streamer — async SSE wrapper around log_ring.stream_from()."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_MAX_LINES = 1000  # upper bound for lines param


async def iter_sse_events(
    ring,
    lines: int = 200,
    level: str | None = None,
    max_events: int | None = None,
) -> AsyncIterator[dict]:
    """Yield log entry dicts from ring buffer as SSE-ready payloads.

    Delivers past entries (up to `lines`) first, then new entries as they arrive.
    `max_events` is used only in tests to avoid infinite loops.
    """
    clamped_lines = min(max(1, lines), _MAX_LINES)
    loop = asyncio.get_event_loop()

    # Capture last_seq BEFORE reading recent entries to avoid missing entries
    # that arrive between recent() and the streaming start
    last_seq = ring.last_seq

    # Deliver historical entries
    recent = await loop.run_in_executor(None, lambda: ring.recent(clamped_lines, level))
    count = 0
    for entry in recent:
        yield entry
        count += 1
        if max_events is not None and count >= max_events:
            return

    if max_events is not None and count >= max_events:
        return

    # Stream new entries by polling get_since()
    while True:
        batch = await loop.run_in_executor(
            None,
            lambda s=last_seq: ring.get_since(s, level),
        )
        for entry in batch:
            yield entry
            count += 1
            last_seq = entry["seq"]
            if max_events is not None and count >= max_events:
                return
        if not batch:
            # Short sleep to avoid busy-loop; real SSE consumers disconnect on page leave
            await asyncio.sleep(0.5)


def format_sse_line(event_type: str, data: dict) -> str:
    """Format a single SSE message (event + data lines)."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
