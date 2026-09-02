#!/usr/bin/env python3
"""Generate config/settings_schema.json from the Python settings schema."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "config" / "settings_schema.json"


def serialized_schema() -> str:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from core.settings_core.settings_schema import get_schema

    return json.dumps(
        get_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def write_schema(path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized_schema(), encoding="utf-8")


def check_schema(path: Path = OUTPUT_PATH) -> tuple[bool, str]:
    expected = serialized_schema()
    if not path.exists():
        return False, f"{path.relative_to(REPO_ROOT)} missing; run uv run python scripts/gen_settings_schema.py"

    actual = path.read_text(encoding="utf-8")
    if actual == expected:
        return True, f"{path.relative_to(REPO_ROOT)} in sync"

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(expected)
        tmp_path = Path(tmp.name)

    diff = "".join(
        difflib.unified_diff(
            actual.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=str(path.relative_to(REPO_ROOT)),
            tofile=str(tmp_path),
        )
    )
    with contextlib.suppress(OSError):
        tmp_path.unlink()
    return (
        False,
        "settings_schema.json is out of sync; run uv run python scripts/gen_settings_schema.py\n"
        + diff,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if committed JSON is stale")
    args = parser.parse_args()

    if args.check:
        ok, message = check_schema()
        print(message)
        return 0 if ok else 1

    write_schema()
    print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
