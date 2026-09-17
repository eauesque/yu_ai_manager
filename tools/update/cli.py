"""CLI for signed update package verification, apply, and rollback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.repair.update_package import apply_update_package, rollback_latest_update, verify_update_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage signed update.zip packages")
    sub = parser.add_subparsers(dest="command", required=True)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("zip_path")
    apply_p = sub.add_parser("apply")
    apply_p.add_argument("zip_path")
    sub.add_parser("rollback")
    args = parser.parse_args()

    if args.command == "verify":
        result = verify_update_package(Path(args.zip_path))
        print(json.dumps({"ok": True, "manifest": result.manifest}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "apply":
        result = apply_update_package(Path(args.zip_path))
        print(json.dumps({"ok": True, "package_id": result.package_id, "applied": result.applied}, ensure_ascii=False, indent=2))
        return 0
    result = rollback_latest_update()
    print(json.dumps({"ok": True, "backup_dir": str(result.backup_dir), "restored": result.restored}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
