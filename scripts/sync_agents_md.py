"""Sync AGENTS.md from CLAUDE.md (Windows-friendly symlink alternative).

On Linux/macOS, AGENTS.md is normally a symlink to CLAUDE.md. Windows users
typically cannot create symlinks without elevated privileges, so this script
maintains AGENTS.md as a byte-identical copy. The pre-push hook verifies the
two files match.

Usage:
    python scripts/sync_agents_md.py          # copy CLAUDE.md -> AGENTS.md
    python scripts/sync_agents_md.py --check  # verify match (exit 1 if not)

When AGENTS.md is already a symlink to CLAUDE.md, this script does nothing.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def is_symlink_to_claude_md() -> bool:
    if not AGENTS_MD.is_symlink():
        return False
    try:
        return AGENTS_MD.resolve() == CLAUDE_MD.resolve()
    except OSError:
        return False


def files_match() -> bool:
    if not AGENTS_MD.exists():
        return False
    return CLAUDE_MD.read_bytes() == AGENTS_MD.read_bytes()


def sync() -> int:
    if not CLAUDE_MD.exists():
        print(f"ERROR: {CLAUDE_MD} not found", file=sys.stderr)
        return 1
    if is_symlink_to_claude_md():
        print(f"OK: {AGENTS_MD.name} is a symlink to {CLAUDE_MD.name} (no copy needed)")
        return 0
    shutil.copyfile(CLAUDE_MD, AGENTS_MD)
    print(f"OK: copied {CLAUDE_MD.name} -> {AGENTS_MD.name}")
    return 0


def check() -> int:
    if not CLAUDE_MD.exists():
        print(f"ERROR: {CLAUDE_MD} not found", file=sys.stderr)
        return 1
    if is_symlink_to_claude_md():
        return 0
    if not AGENTS_MD.exists():
        print(
            f"ERROR: {AGENTS_MD.name} is missing. Run: python scripts/sync_agents_md.py",
            file=sys.stderr,
        )
        return 1
    if not files_match():
        print(
            f"ERROR: {AGENTS_MD.name} is out of sync with {CLAUDE_MD.name}.\n"
            f"       Run: python scripts/sync_agents_md.py",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify CLAUDE.md and AGENTS.md match; exit 1 if not",
    )
    args = parser.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    sys.exit(main())
