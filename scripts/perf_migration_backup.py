"""Measure pre-migration backup creation vs reuse on a copied database.

Usage:
  python scripts/perf_migration_backup.py --db tags.db
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.CRITICAL)

from core.schema_core.schema_migrate import _backup_before_migrate
from core.schema_core.schema_migrate_version import get_schema_version


def _measure_backup_once(db_copy: Path) -> tuple[int, int]:
    con = sqlite3.connect(str(db_copy))
    try:
        current_version = get_schema_version(con)
        t0 = time.perf_counter()
        _backup_before_migrate(con, current_version)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        return current_version, elapsed_ms
    finally:
        con.close()


def _print_summary(db_copy: Path, version: int, first_ms: int, second_ms: int) -> None:
    backup_dir = db_copy.parent / "backup"
    managed_backups = sorted(backup_dir.glob("yu_ai_manager_*.db")) if backup_dir.exists() else []
    legacy_backup = db_copy.with_suffix(f".pre_migrate_v{version}.bak")
    print(f"schema_version={version}")
    print(f"first_backup_ms={first_ms}")
    print(f"second_backup_ms={second_ms}")
    print(f"reuse_speedup={(first_ms / max(second_ms, 1)):.1f}x")
    print(f"managed_backup_files={len(managed_backups)}")
    print(f"legacy_backup_exists={int(legacy_backup.exists())}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="tags.db", help="Path to the source DB")
    parser.add_argument(
        "--work-db",
        default="",
        help="Existing copied DB to use in place without creating another copy",
    )
    args = parser.parse_args()

    if args.work_db:
        db_copy = (ROOT / args.work_db).resolve()
        if not db_copy.exists():
            raise SystemExit(f"Work DB not found: {db_copy}")
        version, first_ms = _measure_backup_once(db_copy)
        _, second_ms = _measure_backup_once(db_copy)
        _print_summary(db_copy, version, first_ms, second_ms)
        return 0

    src_db = (ROOT / args.db).resolve()
    if not src_db.exists():
        raise SystemExit(f"DB not found: {src_db}")

    with tempfile.TemporaryDirectory(prefix="yu_migrate_backup_", dir=str(ROOT)) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        db_copy = tmp_dir / src_db.name
        try:
            shutil.copy2(src_db, db_copy)
        except OSError as exc:
            raise SystemExit(
                f"Failed to copy source DB to temp work DB: {exc}. "
                "Use --work-db with an existing copied DB if disk space is tight."
            ) from exc

        version, first_ms = _measure_backup_once(db_copy)
        _, second_ms = _measure_backup_once(db_copy)
        _print_summary(db_copy, version, first_ms, second_ms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
