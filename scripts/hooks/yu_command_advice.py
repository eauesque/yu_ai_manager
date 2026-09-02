#!/usr/bin/env python3
"""Shared soft-hook wrapper for `yu hook-advice`.

Reads a tool-use JSON payload from stdin, extracts shell commands from common
agent payload shapes, and prints `yu hook-advice` output. It never blocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

SHELL_TOOLS = {
    "Bash",
    "Shell",
    "exec_command",
    "mcp__lean-ctx__ctx_shell",
    "ctx_shell",
}


def extract_command(payload: dict[str, Any]) -> str | None:
    tool = str(
        payload.get("tool_name")
        or payload.get("name")
        or payload.get("tool")
        or payload.get("recipient_name")
        or ""
    )
    tool_input = payload.get("tool_input") or payload.get("input") or payload.get("parameters")
    if not isinstance(tool_input, dict):
        tool_input = payload

    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str) or not command.strip():
        return None

    if tool and tool not in SHELL_TOOLS and "shell" not in tool.lower():
        return None
    return command.strip()


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0

    command = extract_command(payload)
    if not command:
        return 0

    yu = os.environ.get("YU_HOOK_ADVICE_BIN") or "yu"
    try:
        result = subprocess.run(
            [yu, "hook-advice", "--command", command],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return 0

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
