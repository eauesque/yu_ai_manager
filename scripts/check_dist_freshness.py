#!/usr/bin/env python3
"""Detect whether the bundled web UI under ui/default/static/dist/ is in sync
with the TypeScript sources under src/ts/.

Mechanism: build.mjs writes ui/default/static/dist/.build-info.json with a
sha256 hash of every src/ts/**/*.ts file (path + content). On startup we
recompute the hash and compare. A mismatch (or missing info file) means the
dist bundle is stale and the user must run `pnpm run build`.

Used by:
  - web_ui.py    — exits with code 75 (EX_TEMPFAIL) if stale, so the start
                   scripts can intercept and trigger an auto-rebuild.
  - start.sh     — runs this as `python check_dist_freshness.py` to decide
                   whether to call `pnpm run build` before launching.
  - start.bat    — same as start.sh.

Set YU_SKIP_DIST_CHECK=1 to bypass entirely (useful for devs whose watch
mode is already keeping dist fresh, or who intentionally want to run with a
stale bundle).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "ts"
DIST_DIR = ROOT / "ui" / "default" / "static" / "dist"
INFO_FILE = DIST_DIR / ".build-info.json"


def compute_src_hash() -> str:
    """sha256 over every src/ts/**/*.ts file (path + null + content + null).

    Sort key is the posix-style relative path so ordering matches the
    JS-side implementation in build.mjs regardless of OS path separator.
    """
    h = hashlib.sha256()
    entries = [
        (p.relative_to(SRC_DIR).as_posix(), p)
        for p in SRC_DIR.rglob("*.ts")
    ]
    entries.sort(key=lambda e: e[0])
    for rel_str, path in entries:
        h.update(rel_str.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def check() -> tuple[bool, str]:
    """Return ``(is_fresh, reason)``. ``is_fresh`` False ⇒ rebuild needed."""
    if os.environ.get("YU_SKIP_DIST_CHECK") == "1":
        return True, "skipped (YU_SKIP_DIST_CHECK=1)"
    if not SRC_DIR.exists():
        # Packaged release without src/ — nothing to compare against.
        return True, "no src/ts/ (packaged build)"
    cur_hash = compute_src_hash()
    if not INFO_FILE.exists():
        return False, "dist/.build-info.json missing — never built"
    try:
        info = json.loads(INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f".build-info.json unreadable: {exc}"
    recorded = info.get("src_hash")
    if recorded != cur_hash:
        return False, "src/ts/ changed since last build (hash mismatch)"
    return True, "fresh"


def main() -> int:
    fresh, reason = check()
    print(reason)
    return 0 if fresh else 1


if __name__ == "__main__":
    sys.exit(main())
