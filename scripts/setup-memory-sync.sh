#!/usr/bin/env bash
# Set up Claude Code memory sync for this repository.
#
# What this does:
#   1. Registers the LLM merge driver in the local .git/config
#   2. Sets autoMemoryDirectory in ~/.claude/settings.json to .claude/memory/
#   3. Migrates any existing memories from the Claude Code default location
#
# Run once after git clone (or when re-setting up a machine).
# Safe to re-run — all operations are idempotent.

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MEMORY_DIR="${PROJECT_ROOT}/.claude/memory"
USER_SETTINGS="${HOME}/.claude/settings.json"

log_ok()   { printf '[OK]   %s\n' "$*"; }
log_info() { printf '[INFO] %s\n' "$*"; }
log_warn() { printf '[WARN] %s\n' "$*"; }

# ── 1. Register LLM merge driver in local git config ─────────────────────────
UV="${PROJECT_ROOT}/bin/uv"
[[ ! -x "$UV" ]] && UV="uv"  # fall back to PATH

DRIVER_CMD="${UV} run python .claude/scripts/merge-memory.py %O %A %B %P"

git -C "$PROJECT_ROOT" config merge.llm-memory.name "LLM-based memory merge"
git -C "$PROJECT_ROOT" config merge.llm-memory.driver "$DRIVER_CMD"
log_ok "Registered git merge driver: llm-memory"

# ── 2. Set autoMemoryDirectory in ~/.claude/settings.json ────────────────────
mkdir -p "$(dirname "$USER_SETTINGS")"
[[ ! -f "$USER_SETTINGS" ]] && echo '{}' > "$USER_SETTINGS"

# On Windows/Git Bash, $HOME is /c/Users/... but Python needs the native path.
# Use Python itself to resolve the correct home directory.
"$UV" run python - <<PYEOF
import json, pathlib, sys, os

# Resolve ~/.claude/settings.json via Python (handles Windows/WSL/Linux correctly)
settings_path = pathlib.Path.home() / ".claude" / "settings.json"
memory_dir    = r"${MEMORY_DIR}"

# On Windows Git Bash, MEMORY_DIR uses /o/... POSIX style — convert to native
if os.name == "nt" and memory_dir.startswith("/"):
    # /o/yu_ai_manager/... -> O:\yu_ai_manager\...
    parts = memory_dir.lstrip("/").split("/", 1)
    memory_dir = parts[0].upper() + ":\\" + (parts[1].replace("/", "\\") if len(parts) > 1 else "")

settings_path.parent.mkdir(parents=True, exist_ok=True)

try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except Exception:
    settings = {}

current = settings.get("autoMemoryDirectory", "")
if current == memory_dir:
    print("[SKIP] autoMemoryDirectory already set")
else:
    settings["autoMemoryDirectory"] = memory_dir
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    print(f"[OK]   autoMemoryDirectory -> {memory_dir}")
PYEOF

# ── 3. Migrate existing memories from Claude Code default location ────────────
mkdir -p "$MEMORY_DIR"

# Claude Code sanitizes the CWD path for the project folder name.
# Try the most common patterns.
for candidate in \
    "${HOME}/.claude/projects/$(basename "$PROJECT_ROOT")/memory" \
    "${HOME}/.claude/projects/$(echo "$PROJECT_ROOT" | tr '/' '-' | sed 's/^-//')/memory" \
    "${HOME}/.claude/projects/O--yu-ai-manager/memory"
do
    if [[ -d "$candidate" && "$candidate" != "$MEMORY_DIR" ]]; then
        count=$(find "$candidate" -maxdepth 1 -name "*.md" | wc -l)
        if [[ "$count" -gt 0 ]]; then
            log_info "Found $count memory files in $candidate — migrating (skip if already present)"
            for f in "$candidate"/*.md; do
                dest="${MEMORY_DIR}/$(basename "$f")"
                if [[ ! -f "$dest" ]]; then
                    cp "$f" "$dest"
                    log_ok "  $(basename "$f")"
                fi
            done
        fi
        break
    fi
done

log_ok "Memory sync setup complete. New location: $MEMORY_DIR"
log_info "Restart Claude Code for autoMemoryDirectory to take effect."
