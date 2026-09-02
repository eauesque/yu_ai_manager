#!/usr/bin/env python3
"""Apply pending update replacements before the web app starts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class PendingApplyResult:
    applied: int
    failed: int


def apply_pending_replacements(*, project_root: Path | None = None) -> PendingApplyResult:
    root = (project_root or PROJECT_ROOT).resolve()
    pending_dir = root / "data" / "update_pending"
    if not pending_dir.exists():
        return PendingApplyResult(applied=0, failed=0)
    applied = 0
    failed = 0
    for pending_path in sorted(pending_dir.glob("*.json")):
        try:
            payload = json.loads(pending_path.read_text(encoding="utf-8"))
            package_id = payload.get("package_id")
            if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
                print(f"[update] WARN invalid pending package_id skipped: {pending_path}")
                pending_path.unlink()
                continue
            for item in payload.get("pending", []):
                src = Path(str(item["src"]))
                dst = Path(str(item["dst"]))
                if not _is_valid_pending_entry(src, dst, root):
                    print(f"[update] WARN invalid pending replacement skipped: src={src} dst={dst}")
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dst)
                applied += 1
            pending_path.unlink()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[update] pending replace failed: {pending_path}: {exc}")
    return PendingApplyResult(applied=applied, failed=failed)


def _is_valid_pending_entry(src: Path, dst: Path, project_root: Path) -> bool:
    src = src.resolve()
    dst = dst.resolve()
    return (
        _is_relative_to(dst, project_root)
        and src.parent == dst.parent
        and src.name == f".{dst.name}.update-tmp"
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def main() -> int:
    result = apply_pending_replacements()
    if result.applied or result.failed:
        print(f"[update] pending replacements applied={result.applied} failed={result.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
