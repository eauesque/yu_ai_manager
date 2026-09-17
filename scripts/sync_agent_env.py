#!/usr/bin/env python3
"""Sync agent-env.json → agent-env.html (nodes section + content freshness date).

Usage:
    # Register this machine (auto-detect hostname/OS/shell) and sync HTML:
    python scripts/sync_agent_env.py --register

    # Sync JSON → HTML only (no node changes):
    python scripts/sync_agent_env.py

The HTML contains a <script id="agent-env-nodes" type="application/json"> block.
This script replaces its contents so the tab UI renders from the JSON.

It also stamps a *content* freshness date (agent-env.json's "content_synced"),
shown in the HTML header/footer via <code id="agent-env-last-synced">. This is
intentionally distinct from node registration, which happens on every session
start (Claude hooks run --context; Codex runs --register) and would otherwise make
the header always read "today" regardless of whether the hand-authored MCP/
skills/routing sections were actually reviewed. content_synced only advances
when the document's own content (outside the nodes JSON block and the date
spans themselves) actually changes, via a stored content_hash comparison.

Exit codes:
    0  All files up to date or successfully updated.
    1  Marker block missing or other I/O failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "docs" / "development" / "agent-env.json"
HTML_PATH = REPO_ROOT / "docs" / "development" / "agent-env.html"
MODEL_PATH = REPO_ROOT / ".claude" / "agent-models.json"


def _local_today() -> str:
    """Today's local calendar date, ISO-formatted.

    The same value `date.today()` gave. Deliberately *not* `now(UTC).date()`:
    under a positive UTC offset that is yesterday -- measured 2026-09-02 local
    against 09-01 UTC. These stamps are read by a person looking at their own
    calendar.
    """
    return datetime.now(tz=UTC).astimezone().date().isoformat()


def _display_path(path: Path) -> str:
    """Render a path for the registry, collapsing the home directory to `~`.

    The registry is committed, so an absolute path under a home directory
    publishes the account name of whoever ran the sync. `~/code/yu_ai_manager`
    carries the same information a reader needs -- where this node's clone sits
    relative to its home -- without that. Paths outside a home directory (a
    Windows drive root, a container path) are left alone: there is nothing to
    collapse and inventing a placeholder would lose the location entirely.
    """
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _primary_checkout() -> Path:
    """The machine's main checkout, even when this script runs inside a worktree.

    `working_dir` is meant to tell a reader where this node's clone lives. It was
    written from `REPO_ROOT`, which is derived from `__file__` -- so a run from
    inside a git worktree recorded the worktree's path instead. It happened: the
    registry carried `.../.claude/worktrees/ci-nightly-only` for this node, left
    behind by a PreCompact hook that fired while a worktree session was active.
    The path pointed at a directory that gets deleted when that work is done.

    `--git-common-dir` resolves to the primary checkout's `.git` from any
    worktree, so its parent is the real clone. Falls back to `REPO_ROOT` when git
    is unavailable or this is not a repository at all -- a missing `working_dir`
    would be worse than an imprecise one.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10,
        )
    except Exception:
        return REPO_ROOT
    if out.returncode != 0 or not out.stdout.strip():
        return REPO_ROOT
    return Path(out.stdout.strip()).resolve().parent

MARKER_RE = re.compile(
    r'(<script id="agent-env-nodes" type="application/json">)(.*?)(</script>)',
    re.DOTALL,
)
HEADER_DATE_RE = re.compile(
    r'(<code id="agent-env-last-synced">)(.*?)(</code>)', re.DOTALL
)
FOOTER_DATE_RE = re.compile(
    r'(<code id="agent-env-last-synced-footer">)(.*?)(</code>)', re.DOTALL
)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_toml(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _configured_names(sources: list[tuple[dict | None, str]]) -> list[str] | None:
    seen = False
    names: set[str] = set()
    for data, key in sources:
        if data is None:
            continue
        seen = True
        value = data.get(key, {})
        if isinstance(value, (dict, list)):
            names.update(str(name) for name in value)
    return sorted(names) if seen else None


def _enabled_plugins(configs: list[dict | None], key: str) -> list[str] | None:
    seen = False
    names: set[str] = set()
    for data in configs:
        if data is None:
            continue
        seen = True
        plugins = data.get(key, {})
        if not isinstance(plugins, dict):
            continue
        names.update(
            str(name)
            for name, value in plugins.items()
            if value is True or isinstance(value, dict) and value.get("enabled") is True
        )
    return sorted(names) if seen else None


def _skill_names(roots: list[Path]) -> list[str] | None:
    existing = [root for root in roots if root.is_dir()]
    if not existing:
        return None
    names: set[str] = set()
    for root in existing:
        try:
            names.update(path.parent.name for path in root.rglob("SKILL.md"))
        except OSError:
            continue
    return sorted(names)


def _codex_plugin_skill_roots(
    codex_home: Path, plugins: list[str] | None
) -> list[Path]:
    roots: list[Path] = []
    for plugin in plugins or []:
        if "@" not in plugin:
            continue
        name, source = plugin.split("@", 1)
        cache = codex_home / "plugins" / "cache" / source / name
        try:
            versions = sorted(
                (path for path in cache.iterdir() if path.is_dir()), reverse=True
            )
        except OSError:
            continue
        for version in versions:
            manifest = _read_json(version / ".codex-plugin" / "plugin.json")
            if manifest is None:
                continue
            skill_paths = manifest.get("skills", [])
            if isinstance(skill_paths, str):
                skill_paths = [skill_paths]
            if isinstance(skill_paths, list):
                roots.extend(
                    version / str(path)
                    for path in skill_paths
                    if (version / str(path)).is_dir()
                )
            break
    return roots


def _detect_capabilities(
    home: Path | None = None,
    repo_root: Path = REPO_ROOT,
    codex_home: Path | None = None,
) -> dict:
    home = home or Path.home()
    claude_settings = [
        _read_json(home / ".claude" / "settings.json"),
        _read_json(repo_root / ".claude" / "settings.json"),
    ]
    claude_user = _read_json(home / ".claude.json")
    claude_project_mcp = _read_json(repo_root / ".mcp.json")

    codex_home = codex_home or Path(os.environ.get("CODEX_HOME", home / ".codex"))
    codex_configs = [
        _read_toml(codex_home / "config.toml"),
        _read_toml(repo_root / ".codex" / "config.toml"),
    ]
    codex_plugins = _enabled_plugins(codex_configs, "plugins")

    return {
        "claude_code": {
            "mcp_servers": _configured_names(
                [
                    (claude_user, "mcpServers"),
                    (claude_project_mcp, "mcpServers"),
                    *[(settings, "enabledMcpjsonServers") for settings in claude_settings],
                ]
            ),
            "plugins": _enabled_plugins(claude_settings, "enabledPlugins"),
            "skills": _skill_names(
                [home / ".claude" / "skills", repo_root / ".claude" / "skills"]
            ),
        },
        "codex": {
            "mcp_servers": _configured_names(
                [(config, "mcp_servers") for config in codex_configs]
            ),
            "plugins": codex_plugins,
            "skills": _skill_names(
                [
                    codex_home / "skills",
                    home / ".agents" / "skills",
                    repo_root / ".agents" / "skills",
                    *_codex_plugin_skill_roots(codex_home, codex_plugins),
                ]
            ),
        },
    }


def _node_key(hostname: str, os_name: str) -> str:
    """Registry key for one (machine, OS) environment.

    hostname alone is not unique: WSL2 reports the same hostname as its
    Windows host by default, so a user who runs this repo from both native
    PowerShell and WSL2 bash on one box would otherwise upsert into the same
    entry and clobber os/shell/working_dir/mcp_user_level each time they
    switch shells.
    """
    return f"{hostname}::{os_name}"


def _detect_node() -> dict:
    """Auto-detect the current machine's environment."""
    hostname = socket.gethostname()
    os_name = platform.system().lower()  # "windows" | "linux" | "darwin"

    if os_name == "windows":
        icon = "🪟"
        shell = "PowerShell (pwsh)"
        shell_note = "第一選択 — Git Bash / WSL2 経由で bash も使用可能。直接 bash/sh 禁止"
        codex_write = "workspace-write (Win/WSL2 承認不要・2026-05-19 確認)"
    elif os_name == "darwin":
        icon = "🍎"
        shell = shutil.which("zsh") and "zsh" or "bash"
        shell_note = "第一選択"
        codex_write = "workspace-write"
    else:
        icon = "🐧"
        shell = shutil.which("bash") and "bash" or "sh"
        shell_note = "第一選択"
        codex_write = "workspace-write"

    # 'registered' is intentionally excluded — set only on first registration.
    return {
        "id": _node_key(hostname, os_name),
        "label": hostname,
        "icon": icon,
        "os": os_name,
        "shell": shell,
        "shell_note": shell_note,
        "working_dir": _display_path(_primary_checkout()),
        "python": "uv run python",
        "node_pkg": "pnpm",
        "codex_write": codex_write,
        "capabilities": _detect_capabilities(),
    }


def _register_node(data: dict, quiet: bool = False) -> bool:
    """Upsert current machine into the in-memory registry dict. Returns True if changed."""
    out = sys.stderr if quiet else sys.stdout
    detected = _detect_node()
    nodes: list[dict] = data.setdefault("nodes", [])

    idx = next((i for i, n in enumerate(nodes) if n.get("id") == detected["id"]), None)
    if idx is None:
        # Migrate a pre-"::os" entry keyed by bare hostname (matching this
        # OS) in place, rather than leaving a stale duplicate behind.
        idx = next(
            (
                i
                for i, n in enumerate(nodes)
                if n.get("id") == detected["label"] and n.get("os") == detected["os"]
            ),
            None,
        )
    if idx is not None:
        existing = nodes[idx]
        # Merge only auto-detected fields; preserve manually set fields (e.g. registered).
        merged = {**existing, **detected}
        merged.pop("mcp_user_level", None)
        if merged == existing:
            print(f"Node '{detected['id']}' already up to date.", file=out)
            return False
        nodes[idx] = merged
        print(f"Updated node '{detected['id']}' in agent-env.json.", file=out)
        return True

    # First registration — stamp the date.
    detected["registered"] = _local_today()
    nodes.append(detected)
    print(f"Registered new node '{detected['id']}' in agent-env.json.", file=out)
    return True


def _html_safe_json(raw: str) -> str:
    """Escape '<' as the JSON unicode escape \\u003c before embedding in HTML.

    Prevents "</script>" from closing the <script> tag and "<!--" from being
    parsed as an HTML comment. \\u003c is a valid JSON string escape that
    decoders restore to '<', so the round-trip is lossless.
    """
    return raw.replace("<", "\\u003c")


def _strip_for_hash(html_text: str) -> str:
    """Blank the parts of the HTML that change independently of hand-authored
    content: the embedded nodes JSON block and the two date spans themselves.
    Hashing what's left tells us whether the *document content* (MCP cards,
    skills table, routing table, etc.) actually changed.
    """
    norm = MARKER_RE.sub(lambda m: m.group(1) + m.group(3), html_text)
    norm = HEADER_DATE_RE.sub(lambda m: m.group(1) + m.group(3), norm)
    norm = FOOTER_DATE_RE.sub(lambda m: m.group(1) + m.group(3), norm)
    return norm


def _sync(quiet: bool, register: bool) -> int:
    """Do one full sync pass: node registration, content-freshness stamp,
    date-span + nodes-JSON embed. Single JSON read/write, single HTML
    read/write.

    Returns (exit_code, data). data is only non-None when exit_code == 0 —
    on any error path, whatever in-memory registration changes were made
    were never persisted (JSON_PATH.write_text happens later, only on the
    success path), so callers must not treat that data as current state.
    """
    out = sys.stderr if quiet else sys.stdout

    if not JSON_PATH.exists():
        print(f"ERROR: missing {JSON_PATH}", file=sys.stderr)
        return 1, None
    if not HTML_PATH.exists():
        print(f"ERROR: missing {HTML_PATH}", file=sys.stderr)
        return 1, None

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    json_changed = False
    if register:
        json_changed = _register_node(data, quiet=quiet)

    models = _read_json(MODEL_PATH)
    if data.get("model_ranks") != models:
        data["model_ranks"] = models
        json_changed = True

    html_text = HTML_PATH.read_text(encoding="utf-8")
    if not MARKER_RE.search(html_text):
        print(
            'ERROR: <script id="agent-env-nodes" type="application/json"> block '
            "not found in agent-env.html",
            file=sys.stderr,
        )
        # Registration changes above (if any) are only in-memory at this
        # point — nothing was written to JSON_PATH yet — so return None
        # rather than an unpersisted "fresh" registry the caller could
        # mistake for current state.
        return 1, None

    content_hash = hashlib.sha256(_strip_for_hash(html_text).encode("utf-8")).hexdigest()
    if data.get("content_hash") != content_hash:
        data["content_hash"] = content_hash
        data["content_synced"] = _local_today()
        json_changed = True
        print(f"Content changed -> content_synced={data['content_synced']}.", file=out)

    if json_changed:
        JSON_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    content_synced = data.get("content_synced", _local_today())
    json_text = _html_safe_json(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    new_html = MARKER_RE.sub(
        lambda m: m.group(1) + "\n" + json_text + m.group(3), html_text, count=1
    )
    new_html = HEADER_DATE_RE.sub(
        lambda m: m.group(1) + content_synced + m.group(3), new_html
    )
    new_html = FOOTER_DATE_RE.sub(
        lambda m: m.group(1) + content_synced + m.group(3), new_html
    )

    if new_html != html_text:
        HTML_PATH.write_text(new_html, encoding="utf-8")
        print(f"synced {HTML_PATH.name}", file=out)
    else:
        print("agent-env.html already in sync.", file=out)

    return 0, data


def _print_context(data: dict) -> None:
    """Print current node info for session context injection.

    Takes the already-loaded (and, when --register/--context, just-updated)
    registry dict rather than re-reading the file, so it can't race the
    write that _sync() just did and print stale/missing node info.
    """
    hostname = socket.gethostname()
    os_name = platform.system().lower()
    key = _node_key(hostname, os_name)
    nodes = data.get("nodes", [])
    node = next((n for n in nodes if n.get("id") == key), None)
    if node is None:
        print(f"[agent-env] node '{key}' not registered — run: python scripts/sync_agent_env.py --register")
        return

    lines = [f"[agent-env] current node: {node.get('label', hostname)} ({node.get('os', '?')})"]
    if node.get("shell"):
        note = f" ({node['shell_note']})" if node.get("shell_note") else ""
        lines.append(f"  shell: {node['shell']}{note}")
    if node.get("working_dir"):
        lines.append(f"  working_dir: {node['working_dir']}")
    extras = []
    if node.get("python"):
        extras.append(f"python={node['python']}")
    if node.get("node_pkg"):
        extras.append(f"node_pkg={node['node_pkg']}")
    if extras:
        lines.append("  " + " | ".join(extras))
    if node.get("codex_write"):
        lines.append(f"  codex_write: {node['codex_write']}")
    output = "\n".join(lines)
    sys.stdout.buffer.write((output + "\n").encode("utf-8", errors="replace"))


def main() -> int:
    context = "--context" in sys.argv
    register = "--register" in sys.argv or context

    exit_code, data = _sync(quiet=context, register=register)

    if context and data is not None:
        # Node registration/content sync already happened above (writes are
        # done), so this reflects the fresh state — not a stale pre-write read.
        _print_context(data)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
