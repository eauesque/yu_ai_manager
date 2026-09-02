"""Regenerates crates/yu-server/tests/fixtures/scope_fence_presets_golden.json
from the Python source of truth (core/agent_safety/scope_fence.py::PRESETS).

Run this whenever PRESETS changes, then re-run:
    cargo test -p yu-server mcp::scope_check::tests::preset_denied_matches_python_presets_golden
to confirm the Rust `preset_denied()` deny lists (agent_scope_store.rs) were
updated to match.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = (
    REPO_ROOT
    / "crates"
    / "yu-server"
    / "tests"
    / "fixtures"
    / "scope_fence_presets_golden.json"
)


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from core.agent_safety.scope_fence import PRESETS

    golden = {preset: data["denied"] for preset, data in PRESETS.items()}
    FIXTURE_PATH.write_text(json.dumps(golden, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
