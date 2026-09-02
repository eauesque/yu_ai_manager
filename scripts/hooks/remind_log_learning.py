#!/usr/bin/env python3
"""Stop hook: remind Claude to document technical findings.

Fires when the working tree shows non-trivial changes in auth/gateway/router
code without a matching update under `docs/development/development_docs/`.
Injects a reminder into Claude's context via the `additionalContext` channel
(does NOT block — Claude decides whether the change warrants a doc).

Cross-platform: pure Python, called via `uv run python` so the same hook
works on Windows / Linux / macOS without bash dependency.
"""
from __future__ import annotations

import json
import subprocess
import sys

# Narrow allow-list of paths considered "technically substantial".
# Keep narrow: noise here trains Claude to ignore the reminder.
_INTERESTING_PATTERNS = (
    "core/web/auth",
    "core/web/auth_chain",
    "core/web/auth_routes",
    "core/web/auth_helpers",
    "core/gateway/",
    "routes/gateway_",
    "core/llm_router/",
    "core/agent_safety/",
    "core/web/apikey_auth/",
)
_DOCS_DIR = "docs/development/development_docs/"


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except FileNotFoundError:
        return ""


def _changed_paths() -> list[str]:
    """Return paths modified in the working tree (staged + unstaged + untracked)."""
    out = _git("status", "--porcelain")
    paths: list[str] = []
    for line in out.splitlines():
        # porcelain v1: "XY <path>" where XY is 2-char status
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # Renames are "old -> new"; track the destination
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        # Quoted paths (filenames with special chars) — strip surrounding quotes
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        paths.append(path)
    return paths


def main() -> int:
    changed = _changed_paths()
    if not changed:
        return 0

    interesting = [f for f in changed if any(p in f for p in _INTERESTING_PATTERNS)]
    if not interesting:
        return 0

    # If a docs file was already touched in this working-tree state, assume
    # the developer documented it.
    if any(f.startswith(_DOCS_DIR) for f in changed):
        return 0

    sample = ", ".join(sorted(set(interesting))[:6])
    msg = (
        "知見ログリマインダー (auto-injected via Stop hook):\n"
        f"  非自明な技術的変更が検出されました: {sample}\n"
        f"  {_DOCS_DIR} に未記録です。\n"
        "  設計判断・罠・修正方針・関連コミットを md にまとめてから完了してください。\n"
        "  形式の手本: docs/development/development_docs/GATEWAY_AUTH_DUAL_SYSTEM.md\n"
        "  CLAUDE.md の参照テーブルへの追記も忘れずに。\n"
        "  該当しない変更（軽微なリファクタ等）と判断した場合はそのまま完了して構いません。"
    )

    # Stop hook valid fields: continue, suppressOutput, stopReason, decision,
    # reason, systemMessage, terminalSequence.
    # hookSpecificOutput is NOT available for Stop events (it's UserPromptSubmit-only).
    # Use systemMessage to inject the reminder into Claude's next context window.
    payload = {
        "continue": True,
        "systemMessage": msg,
    }
    # ensure_ascii=True so the JSON survives any platform's default stdout
    # encoding (Windows cp932 will otherwise corrupt the Japanese text and
    # Claude Code will receive an invalid systemMessage).
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
