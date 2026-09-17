"""Chatlog AI preprocessing engine.

Extracts conversation summaries, topics, and decisions using Ollama / OpenAI-compatible APIs.
Follows the pattern from core/analysis/engines_factory.py.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 120

_SYSTEM_PROMPT = """\
You are a conversation analyzer. Analyze the conversation and return a JSON object.
Return ONLY valid JSON, no explanation or markdown.
"""

_USER_PROMPT_TEMPLATE = """\
Analyze the following conversation. Return JSON only.

---
{conversation_text}
---

Return format:
{{"summary": "100 chars max summary in the conversation's language", "topics": ["keyword1", "keyword2"], "decisions": ["decision1", "decision2"]}}
"""


@dataclass
class AIProcessResult:
    """AI preprocessing result."""
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    model: str = ""
    raw_response: str = ""


def get_chatlog_ai_config() -> dict[str, Any] | None:
    """Get chatlog AI settings from app configuration.

    Priority:
    1. Flat settings via Extension config_schema (Settings UI)
    2. extensions.builtin_chatlog.ai sub-object (backward compat for manual JSON editing)
    3. Fallback to analysis engine settings
    """
    try:
        from core.configuration.json_rw import read_config
        config = read_config()
    except Exception:
        return None

    ext_conf = config.get("extensions", {}).get("builtin-chatlog", {})

    # 1. Flat config via config_schema (format saved by Settings UI)
    if ext_conf.get("engine_type"):
        return {
            "engine_type": ext_conf.get("engine_type", "ollama"),
            "base_url": ext_conf.get("base_url", "http://localhost:11434"),
            "model": ext_conf.get("model", "llama3.2:latest"),
            "api_key": ext_conf.get("api_key", ""),
        }

    # 2. ai sub-object from manual JSON edit (backward compat)
    ai_conf = ext_conf.get("ai", {})
    if ai_conf.get("engine_type"):
        return ai_conf

    # 3. Fallback to analysis engine settings
    analysis = config.get("analysis", {})
    if analysis.get("engine_type"):
        return analysis

    return None


def _truncate_conversation(messages: list[dict], max_chars: int = 3000) -> str:
    """Extract conversation text. First 2000 chars + last 1000 chars."""
    lines = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        lines.append(f"[{role}]: {content}")

    full_text = "\n".join(lines)
    if len(full_text) <= max_chars:
        return full_text

    head = full_text[:2000]
    tail = full_text[-1000:]
    return f"{head}\n\n[... truncated ...]\n\n{tail}"


def _call_openai_compat(
    base_url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
) -> str:
    """Call the OpenAI-compatible API."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 500,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "YU-AI-Manager/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        with contextlib.suppress(Exception):
            body = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"OpenAI compat API error (HTTP {e.code}): {body}") from e
    except (TimeoutError, urllib.error.URLError) as e:
        raise RuntimeError(f"Cannot connect to {base_url}: {e}") from e

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError("Empty response from API")
    return choices[0].get("message", {}).get("content", "")


def _call_ollama_native(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    """Call the Ollama native API."""
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        with contextlib.suppress(Exception):
            body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 404:
            raise RuntimeError(
                f"Model not found: {model}. Run: ollama pull {model}"
            ) from e
        raise RuntimeError(f"Ollama API error (HTTP {e.code}): {body}") from e
    except (TimeoutError, urllib.error.URLError) as e:
        raise RuntimeError(f"Cannot connect to Ollama at {base_url}: {e}") from e

    return result.get("message", {}).get("content", "")


def _parse_ai_response(raw: str) -> AIProcessResult:
    """Parse AI response as JSON with 3-level fallback."""
    result = AIProcessResult(raw_response=raw)

    # Stage 1: direct parse
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _fill_result(result, parsed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 2: JSON block extraction (```json ... ```)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return _fill_result(result, parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    # Stage 3: extract first { ... }
    m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                return _fill_result(result, parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Failed to parse AI response as JSON")
    result.summary = raw[:200] if raw else ""
    return result


def _fill_result(result: AIProcessResult, data: dict) -> AIProcessResult:
    """Populate AIProcessResult from a parsed dictionary."""
    result.summary = str(data.get("summary", ""))[:500]
    topics = data.get("topics", [])
    if isinstance(topics, list):
        result.topics = [str(t) for t in topics[:20]]
    decisions = data.get("decisions", [])
    if isinstance(decisions, list):
        result.decisions = [str(d) for d in decisions[:20]]
    return result


def process_conversation(
    messages: list[dict],
    config: dict[str, Any] | None = None,
) -> AIProcessResult:
    """Preprocess a conversation with AI.

    When config is None, automatically fetched from app settings.
    """
    if config is None:
        config = get_chatlog_ai_config()
    if not config:
        raise RuntimeError("AI engine not configured")

    engine_type = config.get("engine_type", "ollama")
    base_url = config.get("base_url", "http://localhost:11434")
    model = config.get("model", "llama3.2:latest")
    api_key = config.get("api_key", "")

    conv_text = _truncate_conversation(messages)
    user_prompt = _USER_PROMPT_TEMPLATE.format(conversation_text=conv_text)

    api_messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # Try OpenAI-compatible API, fall back to native Ollama on failure
    raw = ""
    if engine_type in ("openai", "openai_compat", "claude_api"):
        raw = _call_openai_compat(base_url, model, api_key, api_messages)
    elif engine_type == "ollama":
        try:
            raw = _call_openai_compat(base_url, model, api_key, api_messages)
        except Exception:
            raw = _call_ollama_native(base_url, model, api_messages)
    else:
        raw = _call_ollama_native(base_url, model, api_messages)

    result = _parse_ai_response(raw)
    result.model = model
    return result


def generate_summary_only(
    messages: list[dict],
    config: dict[str, Any] | None = None,
) -> str:
    """On-demand summary generation (lightweight version)."""
    try:
        result = process_conversation(messages, config)
        return result.summary
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)
        return ""
