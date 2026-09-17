"""OpenAI stream chunk to Anthropic event translation."""

from __future__ import annotations

import secrets

from .models import StreamState
from .translate_response import _FINISH_REASON_MAP


def openai_chunk_to_anthropic_events(
    chunk: dict,
    state: StreamState,
    requested_model: str,
) -> list[dict]:
    """Translate a single OpenAI streaming chunk to zero or more Anthropic SSE events.

    `state` is mutated across calls within a single request to track which
    content block (text vs tool_use) is currently open and which index it has.
    """
    events: list[dict] = []
    choices = chunk.get("choices") or []
    if not choices:
        return events
    choice = choices[0]
    delta = choice.get("delta") or {}
    finish_reason = choice.get("finish_reason")

    # message_start on the very first chunk; proactively open a text block.
    if not state.message_started:
        state.message_started = True
        state.message_id = chunk.get("id") or f"msg_{secrets.token_hex(12)}"
        state.model = requested_model
        events.append(
            {
                "type": "message_start",
                "message": {
                    "id": state.message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": requested_model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }
        )
        events.append(
            {
                "type": "content_block_start",
                "index": state.current_block_index,
                "content_block": {"type": "text", "text": ""},
            }
        )
        state.in_text_block = True

    # Text delta
    text_delta = delta.get("content")
    if text_delta:
        if not state.in_text_block:
            if state.in_tool_block:
                events.append({"type": "content_block_stop", "index": state.current_block_index})
                state.current_block_index += 1
                state.in_tool_block = False
            events.append(
                {
                    "type": "content_block_start",
                    "index": state.current_block_index,
                    "content_block": {"type": "text", "text": ""},
                }
            )
            state.in_text_block = True
        events.append(
            {
                "type": "content_block_delta",
                "index": state.current_block_index,
                "delta": {"type": "text_delta", "text": text_delta},
            }
        )

    # Tool calls
    for tc in delta.get("tool_calls") or []:
        if state.in_text_block:
            events.append({"type": "content_block_stop", "index": state.current_block_index})
            state.current_block_index += 1
            state.in_text_block = False

        is_new_call = tc.get("id") or tc.get("function", {}).get("name")
        if is_new_call and not state.in_tool_block:
            state.in_tool_block = True
            state.current_tool_id = tc.get("id") or f"toolu_{secrets.token_hex(8)}"
            state.current_tool_name = tc.get("function", {}).get("name", "")
            events.append(
                {
                    "type": "content_block_start",
                    "index": state.current_block_index,
                    "content_block": {
                        "type": "tool_use",
                        "id": state.current_tool_id,
                        "name": state.current_tool_name,
                        "input": {},
                    },
                }
            )

        args_delta = tc.get("function", {}).get("arguments")
        if args_delta:
            events.append(
                {
                    "type": "content_block_delta",
                    "index": state.current_block_index,
                    "delta": {"type": "input_json_delta", "partial_json": args_delta},
                }
            )

    # finish_reason — close current block, emit message_delta + message_stop
    if finish_reason is not None:
        if state.in_text_block or state.in_tool_block:
            events.append({"type": "content_block_stop", "index": state.current_block_index})
            state.in_text_block = False
            state.in_tool_block = False
        stop_reason = _FINISH_REASON_MAP.get(finish_reason, "end_turn")
        events.append(
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 0},
            }
        )
        events.append({"type": "message_stop"})

    return events
