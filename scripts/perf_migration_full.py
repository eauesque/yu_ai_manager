"""Measure full schema-migration startup costs on a copied database.

Usage:
  python scripts/perf_migration_full.py --db tags.db
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

from core.schema_core.schema_migrate import _backup_before_migrate, migrate_db
from core.schema_core.schema_migrate_version import get_schema_version


def _copy_db(src_db: Path, dst_db: Path) -> int:
    t0 = time.perf_counter()
    shutil.copy2(src_db, dst_db)
    return round((time.perf_counter() - t0) * 1000)


def _measure_backup(db_path: Path) -> tuple[int, int]:
    con = sqlite3.connect(str(db_path))
    try:
        version = get_schema_version(con)
        t0 = time.perf_counter()
        _backup_before_migrate(con, version)
        return version, round((time.perf_counter() - t0) * 1000)
    finally:
        con.close()


def _measure_migration(db_path: Path) -> tuple[int, int]:
    con = sqlite3.connect(str(db_path))
    try:
        t0 = time.perf_counter()
        migrate_db(con)
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        version = get_schema_version(con)
        return version, elapsed_ms
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="tags.db", help="Path to the source DB")
    args = parser.parse_args()

    src_db = (ROOT / args.db).resolve()
    if not src_db.exists():
        raise SystemExit(f"DB not found: {src_db}")

    with tempfile.TemporaryDirectory(prefix="yu_migrate_full_", dir=str(ROOT)) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        work_db = tmp_dir / src_db.name

        copy_ms = _copy_db(src_db, work_db)
        version_before, backup_ms = _measure_backup(work_db)
        version_after, migrate_ms = _measure_migration(work_db)

        print(f"db={src_db.name}")
        print(f"copy_ms={copy_ms}")
        print(f"schema_version_before={version_before}")
        print(f"backup_ms={backup_ms}")
        print(f"migrate_ms={migrate_ms}")
        print(f"schema_version_after={version_after}")
        print(f"startup_total_ms={copy_ms + backup_ms + migrate_ms}")
        print(f"copy_plus_backup_ms={copy_ms + backup_ms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
