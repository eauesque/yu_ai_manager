#!/usr/bin/env -S uv run python
"""
Stop hook: Opus review gate.

Codex review gate が有効な場合はそちらに委ね、
Codex が無効・未設定の場合のみ Opus API で同等審査を行ふ。

出力: block 時のみ {"decision":"block","reason":"..."} を stdout へ。
allow / skip 時は無出力で exit 0。
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN_STATE_BASE = Path.home() / ".claude/plugins/data/codex-openai-codex/state"
API_ENDPOINT = "https://api.anthropic.com/v1/messages"
OPUS_MODEL = "claude-opus-4-8"
TIMEOUT_SEC = 180

REVIEW_PROMPT_TMPL = """\
Run a stop-gate review of the previous Claude turn.
Only review the work from the previous Claude turn.
Only review it if Claude actually did code changes in that turn.
Pure status, setup, or reporting output does not count as reviewable work.
If the previous Claude turn was only a status update, a summary, a setup/login check, \
a review result, or output from a command that did not itself make direct edits in that \
turn, return ALLOW immediately and do no further work.
Challenge whether that specific work and its design choices should ship.

{CONTEXT_BLOCK}

Return a compact final answer. Your first line must be exactly one of:
- ALLOW: <short reason>
- BLOCK: <short reason>
Do not put anything before that first line.
Use ALLOW if the previous turn did not make code changes or if you do not see a blocking issue.
Use BLOCK only if the previous turn made code changes and you found something that still \
needs to be fixed before stopping.
"""


def read_hook_input() -> dict:
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def find_codex_state_json(workspace_root: str) -> Path | None:
    if not PLUGIN_STATE_BASE.exists():
        return None
    ws_name = Path(workspace_root).name.lower()
    for d in PLUGIN_STATE_BASE.iterdir():
        if not d.is_dir():
            continue
        sj = d / "state.json"
        if not sj.exists():
            continue
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            wr = data.get("jobs", [{}])[0].get("workspaceRoot", "") if data.get("jobs") else ""
            if Path(wr).name.lower() == ws_name or d.name.lower().startswith(ws_name):
                return sj
        except Exception:  # noqa: S112 -- scanning session files for a match; a failure means not this one
            continue
    return None


def is_codex_gate_active(cwd: str) -> bool:
    """Codex plugin の stopReviewGate が true ならば True を返す。"""
    sj = find_codex_state_json(cwd)
    if sj is None:
        return False
    try:
        data = json.loads(sj.read_text(encoding="utf-8"))
        return bool(data.get("config", {}).get("stopReviewGate", False))
    except Exception:
        return False


def call_opus(last_assistant_message: str) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.stderr.write("stop-opus-review-gate: ANTHROPIC_API_KEY 未設定のため審査をスキップ\n")
        return None

    if not last_assistant_message:
        sys.stderr.write("stop-opus-review-gate: last_assistant_message 無し — スキップ\n")
        return None

    prompt = REVIEW_PROMPT_TMPL.format(
        CONTEXT_BLOCK=f"Previous Claude response:\n{last_assistant_message}"
    )

    payload = json.dumps({
        "model": OPUS_MODEL,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        API_ENDPOINT,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"stop-opus-review-gate: API HTTP {e.code} — 審査スキップ\n")
        return None
    except Exception as e:
        sys.stderr.write(f"stop-opus-review-gate: API エラー ({e}) — 審査スキップ\n")
        return None


def parse_review(raw: str) -> tuple[bool, str | None]:
    first = raw.split("\n", 1)[0].strip()
    if first.startswith("ALLOW:"):
        return True, None
    if first.startswith("BLOCK:"):
        reason = first[len("BLOCK:"):].strip() or raw
        return False, reason
    return True, None  # 予期せぬ形式 → allow


def emit_block(reason: str) -> None:
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")


def main() -> None:
    inp = read_hook_input()
    cwd = inp.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    if is_codex_gate_active(cwd):
        sys.stderr.write("stop-opus-review-gate: Codex gate が有効なのでスキップ\n")
        return

    last_msg = str(inp.get("last_assistant_message") or "").strip()
    raw = call_opus(last_msg)
    if raw is None:
        return

    ok, reason = parse_review(raw)
    if not ok:
        emit_block(f"Opus stop-gate review: {reason}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"stop-opus-review-gate: 予期せぬエラー ({e})\n")
        sys.exit(1)
