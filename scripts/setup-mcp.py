"""Register MCP servers for Claude Code, Codex, and Grok.

- ai-coreutils → project .mcp.json + ~/.codex/config.toml
- memory-server → ~/.local/bin (rewrites stale yu-gateway/target/* paths
  in ~/.claude.json, ~/.claude/settings.json, ~/.grok/config.toml)

Usage:
    uv run python scripts/setup-mcp.py           # register (idempotent)
    uv run python scripts/setup-mcp.py --check   # show current state, no changes
    uv run python scripts/setup-mcp.py --remove  # remove entries
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_JSON = REPO_ROOT / ".mcp.json"
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CODEX_HOOKS = Path.home() / ".codex" / "hooks.json"
CLAUDE_JSON = Path.home() / ".claude.json"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
GROK_CONFIG = Path.home() / ".grok" / "config.toml"
YU_ADVICE_SCRIPT = REPO_ROOT / "scripts" / "hooks" / "yu_command_advice.py"

SERVER_NAME = "ai-coreutils"
SERVER_COMMAND = "ai-coreutils"
SERVER_ARGS = ["mcp", "serve"]
YU_HOOK_COMMAND = f"python3 {YU_ADVICE_SCRIPT}"

MEMORY_NAME = "memory"
MEMORY_ARGS = ["mcp"]
_STALE_MEMORY_BIN = re.compile(
    r"(?:[A-Za-z]:)?"
    r"(?:/|\\)"
    r"[^\s\"']*?"
    r"[/\\]yu-gateway[/\\]target[/\\](?:debug|release)[/\\]memory-server(?:\.exe)?"
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")

def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")

def _would(msg: str) -> None:
    print(f"  [DRY]  {msg}")

def _err(msg: str) -> None:
    print(f"  [ERR]  {msg}", file=sys.stderr)


def _find_binary() -> str | None:
    """Return the ai-coreutils binary path, or None if not in PATH."""
    return shutil.which(SERVER_COMMAND)


def memory_bin_path() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return Path.home() / ".local" / "bin" / f"memory-server{suffix}"


def memory_mcp_entry(command: str) -> dict:
    return {"type": "stdio", "command": command, "args": list(MEMORY_ARGS)}


def rewrite_stale_memory_paths(text: str, new_bin: str) -> str:
    """Replace cargo-target memory-server paths with the installed binary."""
    return _STALE_MEMORY_BIN.sub(lambda _m: new_bin, text)


# ---------------------------------------------------------------------------
# .mcp.json (Claude Code)
# ---------------------------------------------------------------------------

def _mcp_json_update(check: bool, remove: bool) -> bool:
    label = str(MCP_JSON.relative_to(REPO_ROOT))

    if not MCP_JSON.exists():
        if remove:
            _skip(f"{label}: file not found")
            return True
        if check:
            _would(f"{label}: file not found — would create with '{SERVER_NAME}'")
            return True
        data = {"mcpServers": {}}
    else:
        try:
            text = MCP_JSON.read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception as exc:
            _err(f"{label}: parse error — {exc}")
            return False

    servers: dict = data.setdefault("mcpServers", {})

    if remove:
        if SERVER_NAME not in servers:
            _skip(f"{label}: '{SERVER_NAME}' not present")
            return True
        if not check:
            del servers[SERVER_NAME]
            _write_mcp_json(data)
        _ok(f"{label}: removed '{SERVER_NAME}'" + (" (dry-run)" if check else ""))
        return True

    entry = {"command": SERVER_COMMAND, "args": SERVER_ARGS}
    if servers.get(SERVER_NAME) == entry:
        _skip(f"{label}: '{SERVER_NAME}' already registered")
        return True

    if check:
        _would(f"{label}: would register '{SERVER_NAME}' → {entry}")
        return True

    servers[SERVER_NAME] = entry
    _write_mcp_json(data)
    _ok(f"{label}: registered '{SERVER_NAME}'")
    return True


def _write_mcp_json(data: dict) -> None:
    MCP_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# ~/.codex/hooks.json (Codex soft command advice)
# ---------------------------------------------------------------------------

def _codex_hooks_update(check: bool, remove: bool) -> bool:
    label = str(CODEX_HOOKS)

    if not CODEX_HOOKS.exists():
        if remove or check:
            _skip(f"hooks.json: {label} not found")
            return True
        data: dict = {"hooks": {}}
    else:
        try:
            data = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
        except Exception as exc:
            _err(f"hooks.json: parse error — {exc}")
            return False

    hooks_root = data.setdefault("hooks", {})
    pre_tool = hooks_root.setdefault("PreToolUse", [])
    target = None
    for entry in pre_tool:
        if entry.get("matcher") == "Bash":
            target = entry
            break

    if target is None:
        target = {"matcher": "Bash", "hooks": []}
        pre_tool.append(target)

    hooks = target.setdefault("hooks", [])
    existing = [
        hook for hook in hooks
        if hook.get("type") == "command" and hook.get("command") == YU_HOOK_COMMAND
    ]

    if remove:
        if not existing:
            _skip("hooks.json: yu command advice hook not present")
            return True
        if not check:
            target["hooks"] = [
                hook for hook in hooks
                if not (
                    hook.get("type") == "command"
                    and hook.get("command") == YU_HOOK_COMMAND
                )
            ]
            if not target["hooks"]:
                pre_tool.remove(target)
            CODEX_HOOKS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        _ok("hooks.json: removed yu command advice hook" + (" (dry-run)" if check else ""))
        return True

    if existing:
        _skip("hooks.json: yu command advice hook already registered")
        return True

    if check:
        _would(f"hooks.json: would add PreToolUse Bash hook command={YU_HOOK_COMMAND!r}")
        return True

    hooks.append({"type": "command", "command": YU_HOOK_COMMAND, "timeout": 5})
    CODEX_HOOKS.parent.mkdir(parents=True, exist_ok=True)
    CODEX_HOOKS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _ok("hooks.json: registered yu command advice hook")
    return True


# ---------------------------------------------------------------------------
# ~/.codex/config.toml (Codex)
# ---------------------------------------------------------------------------

_TOML_SECTION = f"[mcp_servers.{SERVER_NAME}]"
_TOML_ARGS = ", ".join(f'"{a}"' for a in SERVER_ARGS)
_TOML_BLOCK = (
    f"\n[mcp_servers.{SERVER_NAME}]\n"
    f'command = "{SERVER_COMMAND}"\n'
    f"args = [{_TOML_ARGS}]\n"
)


def _remove_toml_section(text: str, section_header: str) -> str:
    """Remove a TOML section and all its child tables from text.

    Line-based approach avoids regex issues with '[' inside TOML values (e.g. arrays).
    Child tables (e.g. [section.sub]) are also removed so no orphan entries remain.
    """
    section_name = section_header.lstrip("[").rstrip("]")
    child_prefix = f"[{section_name}."
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped == section_header:
            skip = True
            continue
        if skip and stripped.lstrip().startswith("[") and not stripped.lstrip().startswith(child_prefix):
            skip = False
        if not skip:
            out.append(line)
    return "".join(out)


def _codex_toml_update(check: bool, remove: bool) -> bool:
    label = str(CODEX_CONFIG)

    if not CODEX_CONFIG.exists():
        _skip(f"config.toml: {label} not found")
        return True

    text = CODEX_CONFIG.read_text(encoding="utf-8")

    if remove:
        if _TOML_SECTION not in text:
            _skip(f"config.toml: '{SERVER_NAME}' not present")
            return True
        new_text = _remove_toml_section(text, _TOML_SECTION)
        if not check:
            CODEX_CONFIG.write_text(new_text, encoding="utf-8")
        _ok(f"config.toml: removed '{SERVER_NAME}'" + (" (dry-run)" if check else ""))
        return True

    if _TOML_SECTION in text:
        _skip(f"config.toml: '{SERVER_NAME}' already registered")
        return True

    if check:
        _would(f"config.toml: would add [mcp_servers.{SERVER_NAME}] command={SERVER_COMMAND!r} args={SERVER_ARGS}")
        return True

    # Insert after the last existing [mcp_servers.*] section
    mcp_blocks = list(re.finditer(r'\[mcp_servers\.[^\]]+\]', text))
    if mcp_blocks:
        last = mcp_blocks[-1]
        rest = text[last.end():]
        nxt = re.search(r'\n\[', rest)
        insert_at = last.end() + (nxt.start() if nxt else len(rest))
        new_text = text[:insert_at] + _TOML_BLOCK + text[insert_at:]
    else:
        new_text = text.rstrip() + _TOML_BLOCK

    CODEX_CONFIG.write_text(new_text, encoding="utf-8")
    _ok(f"config.toml: registered '{SERVER_NAME}'")
    return True


# ---------------------------------------------------------------------------
# binary sanity check
# ---------------------------------------------------------------------------

def _check_binary() -> None:
    path = _find_binary()
    if path:
        try:
            ver = subprocess.check_output(
                [path, "--version"], text=True, stderr=subprocess.STDOUT
            ).strip().splitlines()[0]
        except Exception:
            ver = "?"
        print(f"  binary : {path} ({ver})")
    else:
        print("  binary : NOT FOUND (run setup-ai-tools.ps1 update or setup-dev-tools.sh --update first)")
    mem = memory_bin_path()
    if mem.is_file():
        print(f"  memory : {mem}")
    else:
        print(f"  memory : NOT FOUND ({mem})")


def _ensure_memory_in_json_text(text: str, command: str) -> tuple[str, bool]:
    """Rewrite stale cargo-target paths; insert mcpServers.memory if missing."""
    rewritten = rewrite_stale_memory_paths(text, command)
    try:
        data = json.loads(rewritten)
    except json.JSONDecodeError:
        return rewritten, rewritten != text
    servers = data.get("mcpServers")
    current = servers.get(MEMORY_NAME, {}).get("command") if isinstance(servers, dict) else None
    if current == command:
        return rewritten, rewritten != text
    if not isinstance(data, dict):
        return rewritten, rewritten != text
    data.setdefault("mcpServers", {})[MEMORY_NAME] = memory_mcp_entry(command)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", True


def _json_memory_update(path: Path, command: str, check: bool, remove: bool) -> bool:
    label = str(path)
    if not path.exists():
        _skip(f"{label}: file not found")
        return True

    text = path.read_text(encoding="utf-8")

    if remove:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            _err(f"{label}: parse error — {exc}")
            return False
        servers = data.get("mcpServers")
        if not isinstance(servers, dict) or MEMORY_NAME not in servers:
            _skip(f"{label}: '{MEMORY_NAME}' not present")
            return True
        if not check:
            del servers[MEMORY_NAME]
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _ok(f"{label}: removed '{MEMORY_NAME}'" + (" (dry-run)" if check else ""))
        return True

    new_text, changed = _ensure_memory_in_json_text(text, command)
    if not changed:
        _skip(f"{label}: '{MEMORY_NAME}' already points at {command}")
        return True
    if check:
        _would(f"{label}: would point '{MEMORY_NAME}' → {command}")
        return True
    path.write_text(new_text, encoding="utf-8")
    _ok(f"{label}: '{MEMORY_NAME}' → {command}")
    return True


def _grok_memory_toml_update(command: str, check: bool, remove: bool) -> bool:
    label = str(GROK_CONFIG)
    section = f"[mcp_servers.{MEMORY_NAME}]"
    block = (
        f"\n[mcp_servers.{MEMORY_NAME}]\n"
        f'command = "{command}"\n'
        f'args = ["mcp"]\n'
        f"enabled = true\n"
    )

    if not GROK_CONFIG.exists():
        _skip(f"grok config: {label} not found")
        return True

    text = GROK_CONFIG.read_text(encoding="utf-8")

    if remove:
        if section not in text:
            _skip(f"grok config: '{MEMORY_NAME}' not present")
            return True
        if not check:
            GROK_CONFIG.write_text(_remove_toml_section(text, section), encoding="utf-8")
        _ok(f"grok config: removed '{MEMORY_NAME}'" + (" (dry-run)" if check else ""))
        return True

    want_cmd = f'command = "{command}"'
    if section in text and want_cmd in text:
        _skip(f"grok config: '{MEMORY_NAME}' already points at {command}")
        return True

    if check:
        _would(f"grok config: would register '{MEMORY_NAME}' → {command}")
        return True

    if section in text:
        text = _remove_toml_section(text, section)
    GROK_CONFIG.write_text(text.rstrip() + block, encoding="utf-8")
    _ok(f"grok config: registered '{MEMORY_NAME}' → {command}")
    return True


def _memory_mcp_update(check: bool, remove: bool) -> bool:
    dest = memory_bin_path()
    if not remove and not dest.is_file():
        _skip(f"memory: binary not found at {dest} — run setup-dev-tools.sh / setup-ai-tools.ps1")
        return True
    command = str(dest)
    ok = True
    ok &= _json_memory_update(CLAUDE_JSON, command, check, remove)
    ok &= _json_memory_update(CLAUDE_SETTINGS, command, check, remove)
    ok &= _grok_memory_toml_update(command, check, remove)
    return ok


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register ai-coreutils and memory-server MCP entries."
    )
    parser.add_argument("--check", action="store_true", help="Show state only; no changes")
    parser.add_argument("--remove", action="store_true", help="Remove registered MCP entries")
    args = parser.parse_args()

    mode = "check" if args.check else ("remove" if args.remove else "register")
    print(f"=== MCP setup: {SERVER_NAME} + {MEMORY_NAME} (mode={mode}) ===")
    _check_binary()
    print()

    ok = True
    ok &= _mcp_json_update(args.check, args.remove)
    ok &= _codex_toml_update(args.check, args.remove)
    ok &= _codex_hooks_update(args.check, args.remove)
    ok &= _memory_mcp_update(args.check, args.remove)

    if args.check:
        print("\n(dry-run: no changes made)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
