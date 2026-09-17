"""Verify every agent named by the routing tables can actually be launched.

Twice now the routing tables have pointed at agents that did not exist, and
nothing said so.  `approach-reviewer` — declared "mandatory, never skippable"
by `agent-workflows.yaml` — had no `.claude/agents/*.md` at all (v4.698.9), and
`feature-dev:code-*` resolved to a plugin that was switched off, so the entries
read as live routing while nothing could be dispatched.  A gate that names a
non-existent gatekeeper is worse than no gate: it reads as coverage.

Two ways an agent name resolves:
  - bare name  -> `.claude/agents/<name>.md` must exist (or be a builtin)
  - plug:agent -> `<plug>` must be enabled in the tracked `.claude/settings.json`

Prose entries (`Opus自身`, `Codex(workspace-write)`, `Skill:deep-research`,
pipelines joined by `→`) name a mode of work rather than a dispatchable
subagent, and are skipped.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_ROUTING_FILES = (".claude/agent-routing.yaml", ".claude/agent-routing-core.yaml")

# `agent: <token>` and `agents: [<token>, ...]` are the two shapes the tables use.
_AGENT_RE = re.compile(r'(?<=agent: )("[^"]*"|[^,}\n]+)')
_AGENT_LIST_RE = re.compile(r"(?<=agents: \[)([^\]]*)\]")

# Dispatchable without a file: shipped with the harness, not with this repo.
_BUILTIN_AGENTS = frozenset({"Explore", "Plan", "general-purpose", "claude"})

# A token naming a way of working, not a subagent that can be dispatched.
_PROSE_MARKERS = ("(", "×", "→", "自身")


def _is_prose(token: str) -> bool:
    return token.startswith("Skill:") or any(m in token for m in _PROSE_MARKERS)


def _tokens(text: str) -> list[str]:
    """Every agent name the routing text names, in no particular order."""
    found: list[str] = []
    for match in _AGENT_RE.finditer(text):
        found.append(match.group(1).strip().strip('"'))
    for match in _AGENT_LIST_RE.finditer(text):
        found.extend(t.strip().strip('"') for t in match.group(1).split(","))
    return [t for t in found if t]


def _enabled_plugins(repo_root: Path) -> dict[str, bool]:
    settings = repo_root / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f".claude/settings.json is not valid JSON: {exc}") from exc
    plugins = data.get("enabledPlugins", {})
    return plugins if isinstance(plugins, dict) else {}


def validate(repo_root: Path = _REPO_ROOT) -> tuple[bool, list[str]]:
    """Return (ok, human-readable problems)."""
    problems: list[str] = []
    plugins = _enabled_plugins(repo_root)
    checked = 0

    for rel in _ROUTING_FILES:
        path = repo_root / rel
        if not path.exists():
            continue
        seen: set[str] = set()
        for token in _tokens(path.read_text(encoding="utf-8")):
            if token in seen or _is_prose(token):
                continue
            seen.add(token)
            checked += 1

            if ":" in token:
                plugin_agent = token.split(":", 1)[0]
                # Tables write the bare plugin name; settings key it by marketplace.
                matches = [k for k in plugins if k.split("@", 1)[0] == plugin_agent]
                if not matches:
                    problems.append(
                        f"{rel}: `{token}` — plugin `{plugin_agent}` は "
                        f".claude/settings.json ノ enabledPlugins ニ無シ"
                    )
                elif not any(plugins[k] for k in matches):
                    problems.append(
                        f"{rel}: `{token}` — plugin `{plugin_agent}` ハ無効（false）ナリ"
                    )
                continue

            if token in _BUILTIN_AGENTS:
                continue
            if not (repo_root / ".claude" / "agents" / f"{token}.md").exists():
                problems.append(f"{rel}: `{token}` — .claude/agents/{token}.md 不在ナリ")

    if not checked:
        problems.append("routing 表カラ agent ヲ一件モ抽出シ得ズ（正規表現ガ死ニ居ル疑ヒ）")
    return not problems, problems


def _self_check() -> list[str]:
    """Replay the two failures this checker exists because of.

    A checker that cannot catch the bugs that motivated it is a green light
    wired to nothing.
    """
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        agents = root / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "design-advisor.md").write_text("x", encoding="utf-8")
        routing = root / ".claude" / "agent-routing.yaml"
        settings = root / ".claude" / "settings.json"

        def write(yaml_body: str, enabled: dict[str, bool]) -> tuple[bool, list[str]]:
            routing.write_text(yaml_body, encoding="utf-8")
            settings.write_text(json.dumps({"enabledPlugins": enabled}), encoding="utf-8")
            return validate(root)

        # Positive control: a consistent table must stay silent.
        ok, problems = write(
            "  - { task: t, agent: design-advisor }\n"
            '  - { task: t, agent: "feature-dev:code-architect" }\n'
            "  Opus: { agents: [design-advisor, Plan] }\n",
            {"feature-dev@claude-plugins-official": True},
        )
        if not ok:
            failures.append(f"整合セル表ヲ誤検出セリ: {problems}")

        # v4.698.9: routing named approach-reviewer; no such agent file existed.
        ok, problems = write(
            "  - { task: t, agent: approach-reviewer }\n", {}
        )
        if ok or not any("approach-reviewer" in p for p in problems):
            failures.append("不在ノ .claude/agents/*.md ヲ見逃セリ")

        # 2026-09-07: routing named a plugin agent while the plugin was off.
        ok, problems = write(
            '  - { task: t, agent: "feature-dev:code-architect" }\n',
            {"feature-dev@claude-plugins-official": False},
        )
        if ok or not any("feature-dev" in p for p in problems):
            failures.append("無効化サレタル plugin ノ agent ヲ見逃セリ")

        # The same entry with the plugin simply absent must also be caught.
        ok, problems = write(
            '  - { task: t, agent: "feature-dev:code-architect" }\n', {}
        )
        if ok or not any("feature-dev" in p for p in problems):
            failures.append("未登録ノ plugin ノ agent ヲ見逃セリ")

    return failures


def main() -> int:
    broken = _self_check()
    if broken:
        print("検出器自身ガ壊レ居ル:")
        for line in broken:
            print(f"  {line}")
        return 1

    ok, problems = validate()
    if ok:
        print("agent routing OK（全 agent 参照ガ実体ヘ解決ス）")
        return 0
    for problem in problems:
        print(problem)
    print("routing 表ヲ実態ヘ合ハスカ、agent／plugin ヲ有効化スベシ")
    return 1


if __name__ == "__main__":
    sys.exit(main())
