"""Negotiation prompt templates and LLM response parser."""
from __future__ import annotations

import json
import re
from typing import Any

from .protocol import Proposal

_SYSTEM_TEMPLATE = """\
You are a node agent. Given your current status and a task proposal, \
decide whether to accept. Respond ONLY in JSON: {{"accept": true/false, "reason": "..."}}

Your status:
- CPU: {cpu_percent}%
- Queue: {queue_depth} tasks
- Capabilities: {inference_types}
- Generating: {generating}"""


def build_system_prompt(node_status: dict[str, Any]) -> str:
    """Build system prompt with current node status."""
    return _SYSTEM_TEMPLATE.format(
        cpu_percent=node_status.get("cpu_percent", 0),
        queue_depth=node_status.get("queue_depth", 0),
        inference_types=", ".join(node_status.get("inference_types", [])),
        generating=node_status.get("generating", False),
    )


def build_user_message(proposal: Proposal) -> str:
    """Build user message from a proposal."""
    reqs = ", ".join(f"{k}={v}" for k, v in proposal.requirements.items())
    return (
        f"Task proposal: {proposal.task_type} - {proposal.task_description}\n"
        f"Requirements: {reqs}\n"
        f"Accept this task?"
    )


def parse_llm_response(raw: str) -> tuple[bool, str]:
    """Parse LLM response into (accept, reason).

    Tries JSON first, then regex fallback.
    Returns (False, "parse_error: ...") if unparseable.
    """
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        return bool(data.get("accept", False)), str(data.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        pass

    # Try extracting JSON object from mixed text
    m = re.search(r'\{[^{}]*"accept"\s*:\s*(true|false)[^{}]*\}', raw, re.IGNORECASE)
    if m:
        try:
            data = json.loads(m.group(0))
            return bool(data.get("accept", False)), str(data.get("reason", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    # Regex fallback: look for accept: true/false pattern
    m = re.search(r'accept\s*[:=]\s*(true|false)', raw, re.IGNORECASE)
    if m:
        return m.group(1).lower() == "true", ""

    return False, "parse_error: could not parse LLM response"
