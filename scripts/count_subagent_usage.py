"""subagent 呼び出し回数と推定モデル tier を集計する。

Usage:
    uv run python scripts/count_subagent_usage.py [--days N] [--json]

出力:
    - 各 subagent の呼び出し回数
    - モデル tier 別集計 (opus / sonnet / haiku / unknown)
    - agent-outputs ファイル数との突き合わせ
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

# subagent 名 → tier マッピング (agents/*.md の model フィールドに対応)
AGENT_TIER: dict[str, str] = {
    "design-advisor": "opus",
    "code-reviewer": "sonnet",
    "impact-evaluator": "sonnet",
    "spec-preflight": "haiku",
    "test-runner": "haiku",
    "lint-runner": "haiku",
    "impact-scanner": "haiku",
    "changelog-writer": "haiku",
    "commit-msg-writer": "haiku",
    "doc-sync-checker": "haiku",
    "dep-audit-summarizer": "haiku",
    "explorer": "haiku",
    "log-triage": "haiku",
    "translator": "haiku",
    "back-translator": "haiku",
    "github-agent": "haiku",
    "implementation-orchestrator": "haiku",
    "semantic-reviewer": "haiku",
}

PROJECT_DIR = Path.home() / ".claude" / "projects"

def _repo_root() -> Path:
    import subprocess
    try:
        # worktree 内では --git-common-dir が main repo の .git を指す
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"], text=True
        ).strip()
        git_dir = Path(common).resolve()
        # .git ディレクトリの親が main repo root
        if git_dir.name == ".git":
            return git_dir.parent
        # .git/worktrees/<name>/commondir のように参照される場合もある
        return git_dir.parent.parent.parent
    except Exception:
        return Path(__file__).parent.parent

REPO_ROOT = _repo_root()
AGENT_OUTPUTS = REPO_ROOT / ".claude" / "agent-outputs"


def find_project_dir() -> Path | None:
    # Claude Code の命名: 絶対パスの "/" を "-" に、"_" を "-" に変換 (先頭 "-" あり)
    raw = REPO_ROOT.resolve().as_posix().replace("/", "-").replace("_", "-")
    candidate = PROJECT_DIR / raw
    if candidate.exists():
        return candidate
    # フォールバック: projects/ 以下を検索
    repo_stem = REPO_ROOT.name.replace("_", "-")
    for d in PROJECT_DIR.iterdir():
        if d.is_dir() and d.name.endswith(repo_stem) and "--" not in d.name:
            return d
    return None


def parse_jsonl_files(project: Path, since: datetime | None) -> list[dict]:
    calls: list[dict] = []
    for jsonl in sorted(project.glob("*.jsonl")):
        if since and datetime.fromtimestamp(jsonl.stat().st_mtime, tz=UTC) < since:
            continue
        with open(jsonl, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg = record.get("message", {})
                ts = record.get("timestamp", "")
                for block in msg.get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use" or block.get("name") != "Agent":
                        continue
                    inp = block.get("input", {})
                    calls.append({
                        "timestamp": ts,
                        "subagent_type": inp.get("subagent_type", ""),
                        "description": inp.get("description", ""),
                        "session": jsonl.stem,
                    })
    return calls


def classify_tier(call: dict) -> tuple[str, str]:
    name = call.get("subagent_type", "").strip()
    if name and name in AGENT_TIER:
        return name, AGENT_TIER[name]
    desc = call.get("description", "").lower()
    for agent, tier in AGENT_TIER.items():
        if agent in desc:
            return agent, tier
    if call.get("subagent_type") == "claude" or not call.get("subagent_type"):
        return "claude (general)", "unknown"
    return name or "unknown", "unknown"


def count_output_files() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not AGENT_OUTPUTS.exists():
        return counts
    for d in AGENT_OUTPUTS.iterdir():
        if not d.is_dir():
            continue
        files = [f for f in d.iterdir() if f.suffix == ".md"]
        counts[d.name] = len(files)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="subagent 呼び出し回数を集計")
    parser.add_argument("--days", type=int, default=0, help="直近 N 日分のみ集計 (0=全期間)")
    parser.add_argument("--json", action="store_true", help="JSON 形式で出力")
    args = parser.parse_args()

    since = (datetime.now(tz=UTC) - timedelta(days=args.days)) if args.days else None

    project = find_project_dir()
    if not project:
        print("ERROR: プロジェクトディレクトリが見つかりません")
        return

    calls = parse_jsonl_files(project, since)
    output_counts = count_output_files()

    by_agent: Counter[str] = Counter()
    by_tier: Counter[str] = Counter()
    tier_map: dict[str, str] = {}

    for call in calls:
        name, tier = classify_tier(call)
        by_agent[name] += 1
        by_tier[tier] += 1
        tier_map[name] = tier

    total = sum(by_agent.values())

    if args.json:
        print(json.dumps({
            "total_agent_calls": total,
            "by_tier": dict(by_tier),
            "by_agent": dict(by_agent.most_common()),
            "output_files": output_counts,
        }, ensure_ascii=False, indent=2))
        return

    period = f"直近 {args.days} 日" if args.days else "全期間"
    print(f"\n=== subagent 呼び出し集計 ({period}, {total} calls) ===\n")

    print("[ モデル tier 別 ]")
    for tier in ("opus", "sonnet", "haiku", "unknown"):
        n = by_tier.get(tier, 0)
        pct = n / total * 100 if total else 0
        bar = "█" * int(pct / 2)
        print(f"  {tier:8s} {n:4d} ({pct:5.1f}%)  {bar}")

    if total:
        opus_saves = by_tier.get("haiku", 0) + by_tier.get("sonnet", 0)
        print(f"\n  → Opus 回避率: {opus_saves}/{total} = {opus_saves/total*100:.1f}%")

    print("\n[ subagent 別 (多い順) ]")
    print(f"  {'agent':32s} {'calls':>6s}  {'tier':8s}  {'output files':>12s}")
    print("  " + "-" * 64)
    for name, count in by_agent.most_common():
        tier = tier_map.get(name, "unknown")
        out = output_counts.get(name, 0)
        print(f"  {name:32s} {count:6d}  {tier:8s}  {out:12d}")

    # output_counts にあって JSONL 未記録のもの
    jsonl_agents = set(dict(by_agent).keys())
    extras = [(d, n) for d, n in sorted(output_counts.items(), key=lambda x: -x[1])
              if d not in jsonl_agents and n > 0]
    if extras:
        print("\n[ agent-outputs のみ (JSONL 未記録セッション分) ]")
        for d, n in extras:
            tier = AGENT_TIER.get(d, "unknown")
            print(f"  {d:32s} {'':>6s}  {tier:8s}  {n:12d}")

    print()


if __name__ == "__main__":
    main()
