"""Extract recent conversation turns from Claude Code JSONL transcript.

Usage:
  uv run python scripts/extract_session_context.py [--turns N] [--out PATH]

Output: tmp/advisor-context-{UTC}.md  (or --out PATH)
Prints the output path to stdout so callers can pass it to a subagent prompt.
"""
import argparse
import glob
import json
import os
import pathlib
import sys
import time
from datetime import UTC, datetime

_MAX_SESSION_AGE_SECS = 6 * 3600
_PROJECTS_DIR = os.path.expanduser("~/.claude/projects/")


def _find_via_proc(projects_dir: str) -> str | None:
    """Walk the process tree to find the JSONL file Claude Code has open.

    Claude Code runs as a Node.js process and keeps the session JSONL open for
    writing.  Because this script is always invoked as a child of that process,
    /proc/<ancestor>/fd gives us the exact file — no global tmp, no race.
    """
    pid = os.getpid()
    visited: set[int] = set()
    while pid > 1 and pid not in visited:
        visited.add(pid)
        try:
            status = pathlib.Path(f"/proc/{pid}/status").read_text()
        except OSError:
            break
        name = next(
            (l.split()[1] for l in status.splitlines() if l.startswith("Name:")),
            "",
        )
        if name in ("node", "claude", "claude-code"):
            fd_dir = pathlib.Path(f"/proc/{pid}/fd")
            try:
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        continue
                    if target.startswith(projects_dir) and target.endswith(".jsonl"):
                        return target
            except PermissionError:
                pass
        # Advance to parent
        ppid_line = next(
            (l for l in status.splitlines() if l.startswith("PPid:")), None
        )
        if ppid_line is None:
            break
        pid = int(ppid_line.split()[1])
    return None


def find_jsonl() -> str | None:
    """Return path to the current session's JSONL transcript.

    Priority:
      1. /proc process-tree walk — finds the JSONL Claude Code actually has open.
         Race-free and session-specific even with concurrent sessions.
      2. Most recently modified JSONL in any project dir that is fresh
         (written within the session window).  Fallback when /proc is unavailable.
      3. Absolute fallback: globally most recent JSONL.
    """
    # 1: /proc walk — Linux only, same-user only, no tmp files needed
    via_proc = _find_via_proc(_PROJECTS_DIR)
    if via_proc:
        return via_proc

    # 2 & 3: file-system heuristics (non-Linux or permission-denied)
    files = glob.glob(os.path.join(_PROJECTS_DIR, "**", "*.jsonl"), recursive=True)
    if not files:
        return None
    now = time.time()
    fresh = [f for f in files if (now - os.path.getmtime(f)) < _MAX_SESSION_AGE_SECS]
    return max(fresh or files, key=os.path.getmtime)


def extract(jsonl_path: str, last_n: int = 30, max_entry_chars: int = 1500) -> str:
    """Parse JSONL and return formatted markdown of last N human/assistant turns."""
    messages: list[tuple[str, str]] = []

    with open(jsonl_path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = rec.get("type")
            if msg_type not in ("user", "human", "assistant"):
                continue

            role = "USER" if msg_type in ("user", "human") else "ASSISTANT"
            payload = rec.get("message", {})
            parts = (
                payload.get("content", [])
                if isinstance(payload, dict)
                else []
            )
            if isinstance(parts, str):
                parts = [{"type": "text", "text": parts}]

            texts: list[str] = []
            for p in parts if isinstance(parts, list) else [parts]:
                if isinstance(p, str):
                    texts.append(p)
                elif isinstance(p, dict):
                    t = p.get("type", "")
                    if t == "text":
                        texts.append(p.get("text", ""))
                    elif t == "tool_use":
                        inp = json.dumps(p.get("input", {}), ensure_ascii=False)
                        texts.append(f"[tool:{p.get('name','?')}] {inp[:300]}")
                    elif t == "tool_result":
                        cv = p.get("content", "")
                        if isinstance(cv, list):
                            cv = " ".join(
                                x.get("text", "") for x in cv if isinstance(x, dict)
                            )
                        texts.append(f"[tool_result] {str(cv)[:400]}")

            body = "\n".join(t for t in texts if t).strip()
            if body:
                messages.append((role, body))

    messages = messages[-last_n:]

    lines = [
        f"# Session Context — last {len(messages)} turns",
        f"Source: `{jsonl_path}`",
        "",
    ]
    for role, body in messages:
        truncated = body[:max_entry_chars] + ("…" if len(body) > max_entry_chars else "")
        lines.append(f"---\n**{role}**\n{truncated}")

    return "\n\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=30, help="Last N turns (default 30)")
    parser.add_argument("--out", default=None, help="Output path (default: tmp/advisor-context-<UTC>.md)")
    args = parser.parse_args()

    jsonl = find_jsonl()
    if not jsonl:
        print("ERROR: no JSONL transcript found", file=sys.stderr)
        sys.exit(1)

    context = extract(jsonl, last_n=args.turns)

    if args.out:
        out = args.out
    else:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        os.makedirs("tmp", exist_ok=True)
        out = f"tmp/advisor-context-{ts}.md"

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(context)

    print(out)


if __name__ == "__main__":
    main()
