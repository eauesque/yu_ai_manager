"""Anthropic request to OpenAI request translation."""

from __future__ import annotations

import json
from typing import Any

from .errors import TranslationError
from .type_guards import is_finite_number as _is_finite_number
from .type_guards import is_integer as _is_integer


def _validate_content_block(block: Any, path: str) -> None:
    if not isinstance(block, dict):
        raise TranslationError(f"{path} must be an object")
    block_type = block.get("type")
    if block_type is not None and not isinstance(block_type, str):
        raise TranslationError(f"{path}.type must be a string")
    if block_type == "text" and "text" in block and not isinstance(block["text"], str):
        raise TranslationError(f"{path}.text must be a string")
    if block_type == "image" and "source" in block and not isinstance(block["source"], dict):
        raise TranslationError(f"{path}.source must be an object")


def _validate_anthropic_request(body: dict) -> None:
    model = body.get("model")
    if model is not None and not isinstance(model, str):
        raise TranslationError("model must be a string")
    system = body.get("system")
    if system is not None:
        if isinstance(system, list):
            for idx, block in enumerate(system):
                _validate_content_block(block, f"system[{idx}]")
        elif not isinstance(system, str):
            raise TranslationError("system must be a string or an array")

    messages = body.get("messages", [])
    if not isinstance(messages, list):
        raise TranslationError("messages must be an array")
    for msg_idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise TranslationError(f"messages[{msg_idx}] must be an object")
        if not isinstance(msg.get("role"), str):
            raise TranslationError(f"messages[{msg_idx}].role must be a string")
        content = msg.get("content", "")
        if isinstance(content, list):
            for block_idx, block in enumerate(content):
                _validate_content_block(block, f"messages[{msg_idx}].content[{block_idx}]")
        elif not isinstance(content, str):
            raise TranslationError(f"messages[{msg_idx}].content must be a string or an array")

    for field in ("temperature", "top_p"):
        if field in body and not _is_finite_number(body[field]):
            raise TranslationError(f"{field} must be a finite number")
    if "max_tokens" in body and not _is_integer(body["max_tokens"]):
        raise TranslationError("max_tokens must be an integer")
    if "stream" in body and not isinstance(body["stream"], bool):
        raise TranslationError("stream must be a boolean")
    if "tools" in body:
        tools = body["tools"]
        if not isinstance(tools, list) or not all(isinstance(t, dict) for t in tools):
            raise TranslationError("tools must be an array of objects")
    if "stop_sequences" in body:
        stops = body["stop_sequences"]
        if not isinstance(stops, list) or not all(isinstance(s, str) for s in stops):
            raise TranslationError("stop_sequences must be an array of strings")


def anthropic_request_to_openai(body: dict) -> dict:
    _validate_anthropic_request(body)
    openai_messages: list[dict] = []
    system = body.get("system")
    if system:
        if isinstance(system, list):
            text_parts = [b["text"] for b in system if b.get("type") == "text"]
            system = "".join(text_parts)
        openai_messages.append({"role": "system", "content": system})

    for msg in body.get("messages", []):
        _translate_message(msg, openai_messages)

    openai_body: dict[str, Any] = {
        "model": body["model"],
        "messages": openai_messages,
        "max_tokens": body.get("max_tokens", 1024),
        "stream": body.get("stream", False),
    }
    if "temperature" in body:
        openai_body["temperature"] = body["temperature"]
    if body.get("tools"):
        openai_body["tools"] = [{
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        } for t in body["tools"]]
    if body.get("stop_sequences"):
        openai_body["stop"] = list(body["stop_sequences"])
    return openai_body


def _anthropic_image_to_openai_part(block: dict) -> dict:
    source = block.get("source") or {}
    source_type = source.get("type")
    if source_type == "base64":
        media_type = source.get("media_type") or "image/png"
        data = source.get("data")
        if not data:
            raise TranslationError("image block with source.type=base64 missing data")
        url = f"data:{media_type};base64,{data}"
    elif source_type == "url":
        url = source.get("url")
        if not url:
            raise TranslationError("image block with source.type=url missing url")
    else:
        raise TranslationError(f"unsupported image source type: {source_type!r} (expected 'base64' or 'url')")
    return {"type": "image_url", "image_url": {"url": url}}


def _translate_message(msg: dict, out: list[dict]) -> None:
    role = msg["role"]
    content = msg.get("content", "")
    if isinstance(content, str):
        out.append({"role": role, "content": content})
        return

    content_parts: list[dict] = []
    tool_calls: list[dict] = []
    pending_tool_results: list[dict] = []
    for block in content:
        block_type = block.get("type")
        if block_type == "text":
            content_parts.append({"type": "text", "text": block.get("text", "")})
        elif block_type == "image":
            content_parts.append(_anthropic_image_to_openai_part(block))
        elif block_type == "tool_use":
            tool_calls.append({
                "id": block["id"],
                "type": "function",
                "function": {"name": block["name"], "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)},
            })
        elif block_type == "tool_result":
            tr_content = block.get("content", "")
            if not isinstance(tr_content, str):
                tr_content = json.dumps(tr_content, ensure_ascii=False)
            pending_tool_results.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": tr_content})
        else:
            raise TranslationError(f"unsupported content block type: {block_type}")

    if content_parts or tool_calls or not pending_tool_results:
        has_image = any(p.get("type") == "image_url" for p in content_parts)
        if has_image:
            msg_content: Any = content_parts
        else:
            text = "".join(p.get("text", "") for p in content_parts)
            msg_content = text if text else None
        msg_out: dict[str, Any] = {"role": role, "content": msg_content}
        if tool_calls:
            msg_out["tool_calls"] = tool_calls
        out.append(msg_out)

    out.extend(pending_tool_results)
