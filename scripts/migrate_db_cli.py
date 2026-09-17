#!/usr/bin/env python3
"""Migrate an existing yu database, for callers with nobody watching.

`deploy/README.md` has long told operators to "run the Python version once" to
migrate a database the binary refuses (exit 78). There was no way to do that:
no entry point took a database path, and -- worse -- `apply_key` issued a
hardcoded key, so a systemd deployment's database, encrypted with the
operator's own `YU_DB_KEY`, could not be opened from Python at all.

This is that entry point. It migrates and nothing else:

* It does not create databases. `init_db` is never called, because it runs DDL
  before the pre-migration backup and would break "if no backup is possible,
  the database is left untouched". A database reporting version 0 is refused.
* It does not read config. `TAGDB_DB` and config's `db` key are known to take
  precedence over each other differently in the two runtimes, so a migrator
  that consulted config could migrate a different file than the one named.
* It does not skip the backup by default. On a desktop a skipped backup is a
  line in a log someone can read; here it is a one-way write nobody sees.

Exit codes are the interface, since the caller is a systemd unit:

    0  already current, or migrated successfully
    1  migration failed
    3  no backup could be taken and --allow-skip-backup was not given
    4  the database could not be opened (wrong key, corrupt, permissions)
    5  the database reports version 0 -- not ours to create
    6  another writer holds the lock
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.schema_core.schema_constants import CURRENT_SCHEMA_VERSION  # noqa: E402
from core.schema_core.schema_migrate import (  # noqa: E402
    BackupUnavailable,
    migrate_db,
)
from core.schema_core.schema_migrate_version import get_schema_version  # noqa: E402
from core.services_core.db_cipher import apply_key, sqlite3  # noqa: E402

EXIT_OK = 0
EXIT_MIGRATION_FAILED = 1
EXIT_NO_BACKUP = 3
EXIT_UNOPENABLE = 4
EXIT_VERSION_ZERO = 5
EXIT_LOCKED = 6

# Long enough to outlast a server's startup writes; matches the value
# core/stats_api/stats_cache.py already uses for the same reason.
BUSY_TIMEOUT_MS = 30_000


def _open(db_path: Path, key: str | None) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    apply_key(con, key)
    con.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    # Force a real read. `PRAGMA key` alone establishes a connection even on a
    # file this key cannot decrypt, and get_schema_version swallows every
    # exception into version 0 -- so without this probe a wrong key is
    # indistinguishable from an empty ledger, and the operator is told to
    # create a database rather than to fix their key.
    con.execute("SELECT count(*) FROM sqlite_master").fetchone()
    return con


def _pin_data_dir(db_path: Path) -> None:
    """Give the migrations that write files somewhere to write them.

    Migration 88 plants a scan-roots recovery marker at
    ``core.paths.data_path(...)``, which raises unless ``init_app_paths`` has
    run -- and this process is not the app, so nothing has run it. The
    migration catches that as "non-fatal", so the marker silently never
    appears and the server never offers the recovery it exists to trigger.

    ``TAGDB_DATA_DIR`` is the same variable the server resolves the marker
    through (``crates/yu-server/src/secret_store.rs``), so an operator who
    sets it gets both halves pointing at one directory. With no env there is
    one defensible guess that does not involve reading config: the directory
    the database itself sits in, which is what ``data/tags.db`` means.

    Only the data directory is pinned. cache/logs/profiles keep their
    CWD-relative defaults, which is exactly where the app itself would put
    them when run from the same working directory.
    """
    from core.paths import init_app_paths

    os.environ.setdefault("TAGDB_DATA_DIR", str(db_path.parent))
    init_app_paths()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--db", required=True, help="path to tags.db")
    parser.add_argument(
        "--db-key",
        default=os.environ.get("YU_DB_KEY"),
        help="encryption key; defaults to $YU_DB_KEY, then to the application key",
    )
    parser.add_argument(
        "--allow-skip-backup",
        action="store_true",
        help="migrate even when no pre-migration backup could be taken",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"error: no such database: {db_path}", file=sys.stderr)
        return EXIT_UNOPENABLE

    _pin_data_dir(db_path)

    try:
        con = _open(db_path, args.db_key or None)
    except ValueError as exc:  # rejected key -- never print the key itself
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNOPENABLE
    except sqlite3.Error as exc:
        print(
            f"error: cannot open {db_path}: {exc}. "
            "The key may be wrong, or the file damaged or unreadable.",
            file=sys.stderr,
        )
        return EXIT_UNOPENABLE

    try:
        before = get_schema_version(con)
        if before == 0:
            print(
                f"error: {db_path} reports schema version 0. This tool migrates "
                "existing databases; it does not create them.",
                file=sys.stderr,
            )
            return EXIT_VERSION_ZERO
        if before >= CURRENT_SCHEMA_VERSION:
            print(f"already at schema v{before}; nothing to do")
            return EXIT_OK

        print(f"migrating {db_path}: v{before} -> v{CURRENT_SCHEMA_VERSION}")
        started = time.perf_counter()
        try:
            migrate_db(
                con,
                require_backup=not args.allow_skip_backup,
                db_key=args.db_key or None,
                # Next to the database being migrated, not next to whatever
                # config happens to name. They need not be the same file, and
                # this tool deliberately does not read config.
                backup_dir=str(db_path.parent / "backup"),
            )

        except BackupUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(
                "Pass --allow-skip-backup to migrate anyway, or free space / "
                "lower the database size so a backup can be taken.",
                file=sys.stderr,
            )
            return EXIT_NO_BACKUP
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                print(
                    f"error: another process holds the write lock: {exc}",
                    file=sys.stderr,
                )
                return EXIT_LOCKED
            print(f"error: migration failed: {exc}", file=sys.stderr)
            return EXIT_MIGRATION_FAILED
        except Exception as exc:
            print(f"error: migration failed: {exc}", file=sys.stderr)
            return EXIT_MIGRATION_FAILED

        elapsed = time.perf_counter() - started
        after = get_schema_version(con)
        print(f"migrated to schema v{after} in {elapsed:.1f}s")
        return EXIT_OK if after >= CURRENT_SCHEMA_VERSION else EXIT_MIGRATION_FAILED
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
