#!/usr/bin/env python3
"""Hard-gate wrapper enforcing .agents/yu-workflow.yaml command policy.

Reads a PreToolUse JSON payload from stdin. When a raw shell command matches
an `avoid_before_yu` pattern, emits a deny decision whose reason points to the
yu equivalent. Two-strike fallback: the same command re-issued in the same
session is allowed, implementing fallback.raw_allowed_when with a stated
reason in the agent's reply.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SHELL_TOOLS = {
    "Bash",
    "Shell",
    "exec_command",
    "mcp__lean-ctx__ctx_shell",
    "ctx_shell",
}

# Wrappers that already satisfy the policy; segments starting with these pass.
ALLOWED_PREFIXES = ("yu", "ai-coreutils", "rtk", "lean-ctx")

# (segment regex, yu replacement) — mirrors command_policy.avoid_before_yu.
GATE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^git\s+diff\b"), 'yu diff / yu ctx'),
    (re.compile(r"^git\s+status\b"), "yu ctx"),
    (re.compile(r"^git\s+log\s+.*--stat\b"), "yu ctx"),
    (re.compile(r"^grep\s+(-\w*\s+)*-[rR]\b"), 'yu find "<query>"'),
    (re.compile(r"^rg\b"), 'yu find "<query>"'),
    (re.compile(r"^ls\s+(-\w*\s+)*-\w*R\b"), "yu digest / yu map"),
    (re.compile(r"^find\s+\."), "yu digest / yu map"),
    (re.compile(r"^tree\b"), "yu digest"),
    (re.compile(r"^pytest\s+.*-vv\b"), "yu failure / yu fix-cycle"),
    (re.compile(r"^cargo\s+test\b"), "yu test-impact / yu minimal-test / yu verify"),
    (re.compile(r"^(npm|pnpm)\s+(run\s+)?test\b"), "yu verify"),
]
# `cat` is gated separately: heredocs (cat <<EOF) are writes, not reads.
CAT_RULE = (re.compile(r"^cat\b"), "yu safe-cat <path> --range N:M")

# commit/push are gated until the matching yu verification ran this session
# (command_policy.commit_ready / push_ready). Markers are recorded when the
# corresponding yu subcommand passes through this hook.
MARKER_SUBCOMMANDS = {
    "verify": "commit_ok",
    "postflight": "commit_ok",
    "pr-ready": "push_ok",
}
COMMIT_PUSH_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"^git\s+(?:-[Cc]\s+\S+\s+|-[Cc]\S+\s+|--\S+\s+)*commit\b"),
        "commit_ok",
        "yu verify / yu postflight",
    ),
    (
        re.compile(r"^git\s+(?:-[Cc]\s+\S+\s+|-[Cc]\S+\s+|--\S+\s+)*push\b"),
        "push_ok",
        "yu pr-ready",
    ),
]


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


# Transparent process wrappers: the policy applies to the command they run.
WRAPPER_TOKENS = {
    "command",
    "builtin",
    "eval",
    "exec",
    "time",
    "nohup",
    "env",
    "stdbuf",
    "timeout",
    "nice",
    "ionice",
    "setsid",
    "xargs",
    "sudo",
    "doas",
    "watch",
    "strace",
    "ltrace",
}

# Command heads the gate rules can match. Used to find the wrapped command
# after a wrapper whose flags take value arguments (e.g. `sudo -u alice git
# push`, `timeout -s KILL 30 git push`).
KNOWN_HEADS = {
    "git",
    "grep",
    "rg",
    "ls",
    "find",
    "tree",
    "cat",
    "pytest",
    "cargo",
    "npm",
    "pnpm",
    "yu",
    "ai-coreutils",
    "rtk",
    "lean-ctx",
    "bash",
    "sh",
    "zsh",
    "dash",
}

ENV_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")

# Inline shell payloads: bash -c 'git push', sh -lc "...", lean-ctx -c "...".
SHELL_PAYLOAD_RE = re.compile(
    r"\b(?:bash|sh|zsh|dash|lean-ctx)\b[^|;&\n]*?-\w*c\s+(?:\"([^\"]*)\"|'([^']*)')"
)
# Subshells, backticks, and process substitution all execute their payload.
# Bare `(cmd)` at segment start is handled by normalize_segment's opener strip.
SUBSHELL_PAYLOAD_RE = re.compile(r"(?:[<>]|\$)\(([^()]*)\)|`([^`]*)`")


def split_segments(command: str) -> list[str]:
    # Heredoc bodies are data, not commands: keep them in one segment so the
    # gate does not fire on literal text like "git push" inside a heredoc.
    sep = r"&&|\|\||[;|&]" if "<<" in command else r"&&|\|\||[;|&\n]"
    return [seg.strip() for seg in re.split(sep, command) if seg.strip()]


def expand_segments(command: str) -> list[str]:
    """Command segments plus payloads of inline shells and subshells."""
    segments = split_segments(command)
    for match in SHELL_PAYLOAD_RE.finditer(command):
        payload = match.group(1) or match.group(2) or ""
        segments.extend(split_segments(payload))
    for match in SUBSHELL_PAYLOAD_RE.finditer(command):
        payload = match.group(1) or match.group(2) or ""
        segments.extend(split_segments(payload))
    return segments


def normalize_segment(seg: str) -> str:
    """Strip quotes, subshell openers, env assignments, wrappers, and paths."""
    # The shell strips quotes and escape backslashes before execution, so
    # `"git" push` and `\git push` both run git; match against the unquoted
    # form. Rules are start-anchored, so quoted text in later arguments
    # cannot cause false positives.
    seg = seg.replace('"', "").replace("'", "").replace("\\", "")
    seg = re.sub(r"^[\s({`]*(?:\$\()?\s*", "", seg)
    tokens = seg.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if ENV_ASSIGN_RE.fullmatch(tok):
            i += 1  # leading VAR=value assignment
            continue
        base = tok.rsplit("/", 1)[-1]
        if base in WRAPPER_TOKENS:
            # Skip the wrapper plus its flags and their value arguments
            # (`sudo -u alice`, `timeout -s KILL 30`) until the wrapped
            # command, another wrapper, or a VAR= assignment is found.
            i += 1
            while i < len(tokens):
                nxt = tokens[i].rsplit("/", 1)[-1]
                if (
                    nxt in WRAPPER_TOKENS
                    or nxt in KNOWN_HEADS
                    or ENV_ASSIGN_RE.fullmatch(tokens[i])
                ):
                    break
                i += 1
            continue
        tokens[i] = base  # /usr/bin/git -> git
        break
    return " ".join(tokens[i:])


def yu_markers(command: str) -> set[str]:
    """Markers earned by yu verification subcommands present in this command."""
    earned: set[str] = set()
    for seg in expand_segments(command):
        tokens = normalize_segment(seg).split()
        if len(tokens) >= 2 and tokens[0] in ("yu", "ai-coreutils"):
            marker = MARKER_SUBCOMMANDS.get(tokens[1])
            if marker:
                earned.add(marker)
    return earned


def match_gate(command: str, markers: set[str]) -> tuple[str, str] | None:
    for raw_seg in expand_segments(command):
        seg = normalize_segment(raw_seg)
        if not seg:
            continue
        tokens = seg.split()
        first = tokens[0]
        # rtk is a transparent proxy (rtk git push runs git push) and
        # `yu run -- <command>` executes the wrapped command: the commit/push
        # verification policy applies to what actually runs.
        inner = seg
        if first == "rtk" and len(tokens) > 1:
            inner = seg.split(None, 1)[1]
        elif first in ("yu", "ai-coreutils") and len(tokens) >= 2 and tokens[1] == "run":
            inner = seg.split("--", 1)[1].strip() if "--" in seg else ""
        for pattern, marker, suggestion in COMMIT_PUSH_RULES:
            if pattern.search(inner) and marker not in markers:
                return raw_seg, f"{suggestion} (run it first, then re-issue this command)"
        if first in ALLOWED_PREFIXES:
            continue
        if CAT_RULE[0].search(seg) and "<<" not in seg:
            return raw_seg, CAT_RULE[1]
        for pattern, suggestion in GATE_RULES:
            if pattern.search(seg):
                return raw_seg, suggestion
    return None


def seen_file(payload: dict[str, Any]) -> Path:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or "."
    session = str(payload.get("session_id") or "default")
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session)
    return Path(root) / ".claude" / "session-state" / "yu-gate" / f"{safe}.seen"


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

    state = seen_file(payload)
    try:
        seen = state.read_text(encoding="utf-8") if state.exists() else ""
    except OSError:
        seen = ""

    earned = yu_markers(command)
    if earned:
        new = [f"marker:{m}" for m in sorted(earned) if f"marker:{m}" not in seen]
        if new:
            try:
                state.parent.mkdir(parents=True, exist_ok=True)
                with state.open("a", encoding="utf-8") as fh:
                    fh.write("".join(line + "\n" for line in new))
            except OSError:
                pass

    markers = {m for m in MARKER_SUBCOMMANDS.values() if f"marker:{m}" in seen} | earned
    hit = match_gate(command, markers)
    if hit is None:
        return 0
    segment, suggestion = hit

    # "Have I seen this exact command" marker. Equality on the command
    # string is the only property needed: an agent able to craft a
    # collision can simply run the command twice, which this gate allows.
    digest = hashlib.sha1(
        " ".join(command.split()).encode(), usedforsecurity=False
    ).hexdigest()
    try:
        if digest in seen:
            return 0  # second strike: fallback allowed
        state.parent.mkdir(parents=True, exist_ok=True)
        with state.open("a", encoding="utf-8") as fh:
            fh.write(digest + "\n")
    except OSError:
        pass  # state failure must not turn the gate into a permanent block

    reason = (
        f"Raw `{segment}` is gated by .agents/yu-workflow.yaml. Use `{suggestion}` instead "
        "(in-session, prefer the MCP form mcp__ai-coreutils__*). "
        "Raw fallback is allowed only when yu output was insufficient, exact line context is "
        "required, or the user explicitly asked for raw output — in that case state the reason "
        "in your reply and re-run the identical command; the second attempt is allowed."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
