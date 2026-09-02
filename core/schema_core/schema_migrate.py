"""Schema migration helpers."""

import importlib
import json
import logging
import pkgutil
import re
import shutil
import sqlite3
import time
from pathlib import Path

from core.services_core.db_api import set_startup_status

from .migration_errors import InsufficientDiskForMigration, MigrationDataIntegrityError
from .schema_constants import CURRENT_SCHEMA_VERSION
from .schema_migrate_registry import apply_pending
from .schema_migrate_registry import register as _reg
from .schema_migrate_version import get_schema_version


# Dynamically discover and register all migration steps.
# Scans for modules matching 'schema_migrate_steps_*' in this package
# and registers any 'apply_migration_N' functions found.
# The re-export hub 'schema_migrate_steps.py' (no suffix) is excluded
# to avoid 22 duplicate registrations from facade + source modules.
def _auto_register():
    _pattern = re.compile(r"^apply_migration_(\d+)$")
    pkg = importlib.import_module(__package__)
    for _finder, name, _ispkg in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        short = name.rpartition(".")[2]
        if short == "schema_migrate_steps" or not short.startswith("schema_migrate_steps"):
            continue
        mod = importlib.import_module(name)
        for attr_name in dir(mod):
            m = _pattern.match(attr_name)
            if m:
                version = int(m.group(1))
                _reg(version, getattr(mod, attr_name))

_auto_register()

logger = logging.getLogger(__name__)


def _resolve_pre_migrate_backup_dir(db_path: Path) -> Path:
    try:
        from importlib import import_module
        _backup_utils = import_module("extensions.builtin_backup.core_impl.backup_utils")
        return _backup_utils._resolve_backup_dir(None)
    except Exception:
        return db_path.parent / "backup"


def _load_backup_meta(meta_path: Path) -> dict:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _find_reusable_pre_migrate_backup(db_path: Path, current_version: int) -> Path | None:
    try:
        db_stat = db_path.stat()
    except OSError:
        return None

    backup_dir = _resolve_pre_migrate_backup_dir(db_path)
    if not backup_dir.exists():
        return None

    db_resolved = str(db_path.resolve())
    latest_match: Path | None = None
    latest_epoch = -1.0
    for backup_path in backup_dir.glob("yu_ai_manager_*.db"):
        if backup_path.name.endswith(".meta.json"):
            continue
        meta = _load_backup_meta(backup_path.with_suffix(".db.meta.json"))
        if meta.get("reason") != "pre_migrate":
            continue
        if meta.get("schema_version") != current_version:
            continue

        same_db = (
            meta.get("source_db_path") == db_resolved
            and meta.get("source_db_size") == db_stat.st_size
            and meta.get("source_db_mtime_ns") == db_stat.st_mtime_ns
        )
        if not same_db:
            continue

        created_epoch = float(meta.get("created_epoch") or 0.0)
        if created_epoch >= latest_epoch:
            latest_match = backup_path
            latest_epoch = created_epoch
    return latest_match


# DB size threshold above which pre-migrate backup is skipped.
# Migrations are idempotent — a failed run can simply be retried on restart.
# For large DBs the backup cost (sqlite3 online backup of the entire file)
# far exceeds the migration cost itself, so we skip it and rely on retry.
_BACKUP_SKIP_THRESHOLD_BYTES = 500 * 1024 * 1024  # 500 MB
_FILE_WD_TAGS_REBUILD_DISK_CHECK_MIN_BYTES = 500 * 1024 * 1024
_MIGRATION_81_DISK_CHECK_MIN_BYTES = _FILE_WD_TAGS_REBUILD_DISK_CHECK_MIN_BYTES
# Migration-time WAL peak is roughly the new table plus new indexes
# (~1GB measured on an 11GB DB, spec 2026-06-02 section 11).
# VACUUM temp space is checked separately by the post-migration VACUUM step,
# not here. Fraction 0.30 is a conservative upper bound for larger libraries.
_FILE_WD_TAGS_REBUILD_WAL_FRACTION = 0.30
_FILE_WD_TAGS_REBUILD_MIN_REQUIRED_BYTES = 2 * 1024**3
_MIGRATION_81_WAL_FRACTION = _FILE_WD_TAGS_REBUILD_WAL_FRACTION
_MIGRATION_81_MIN_REQUIRED_BYTES = _FILE_WD_TAGS_REBUILD_MIN_REQUIRED_BYTES


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _resolve_main_db_path(con: sqlite3.Connection) -> Path | None:
    row = con.execute("PRAGMA database_list").fetchone()
    if row is None:
        return None
    db_path_str = row[2]
    if not db_path_str or db_path_str == ":memory:":
        return None
    return Path(db_path_str)


def _precheck_file_wd_tags_rebuild_migrations(
    con: sqlite3.Connection,
    current_version: int,
) -> None:
    target_versions = [v for v in (81, 82) if current_version < v <= CURRENT_SCHEMA_VERSION]
    if not target_versions:
        return
    first_target = min(target_versions)
    target_label = "/".join(str(v) for v in target_versions)

    if _table_exists(con, "file_wd_tags"):
        violations = con.execute("PRAGMA foreign_key_check(file_wd_tags)").fetchall()
        if violations:
            set_startup_status({
                "kind": "migration",
                "stage": "precheck_failed",
                "check": "foreign_key_check",
                "table": "file_wd_tags",
                "violations": len(violations),
                "first": tuple(violations[0]),
            })
            raise MigrationDataIntegrityError(
                f"Migration {first_target} cannot proceed: file_wd_tags has foreign-key "
                f"violations; first={tuple(violations[0])!r}"
            )

    db_path = _resolve_main_db_path(con)
    if db_path is None or not db_path.exists():
        return
    db_size = db_path.stat().st_size
    if db_size < _MIGRATION_81_DISK_CHECK_MIN_BYTES:
        return

    required = max(
        int(db_size * _MIGRATION_81_WAL_FRACTION),
        _MIGRATION_81_MIN_REQUIRED_BYTES,
    )
    free = shutil.disk_usage(db_path.parent).free
    if free < required:
        set_startup_status({
            "kind": "migration",
            "stage": "precheck_failed",
            "check": "disk",
            "required_bytes": required,
            "free_bytes": free,
            "db_size_bytes": db_size,
        })
        raise InsufficientDiskForMigration(
            f"Migration {target_label} needs more free disk space for the projected WAL; "
            f"required={required} bytes, free={free} bytes"
        )


def _backup_before_migrate(con: sqlite3.Connection, current_version: int) -> None:
    """Automatically back up the DB file before migration.

    For databases larger than ``_BACKUP_SKIP_THRESHOLD_BYTES`` the backup is
    skipped entirely — migrations are idempotent and can be retried on restart,
    so the cost of a full online-backup copy is not justified.

    For smaller databases the backup extension is used if available, falling
    back to ``shutil.copy2``.
    """
    try:
        db_path_str = con.execute("PRAGMA database_list").fetchone()[2]
        if not db_path_str or db_path_str == ":memory:" or db_path_str == "":
            return
        db_path = Path(db_path_str)
        if not db_path.exists():
            return
    except Exception as exc:
        logger.warning("Failed to resolve DB path for backup: %s", exc)
        return

    # Large DB — skip backup, rely on idempotent migration + restart retry
    try:
        db_size = db_path.stat().st_size
    except OSError:
        db_size = 0
    if db_size >= _BACKUP_SKIP_THRESHOLD_BYTES:
        set_startup_status({
            "kind": "migration",
            "stage": "backup_skipped",
            "from_version": current_version,
            "db_size_bytes": db_size,
            "threshold_bytes": _BACKUP_SKIP_THRESHOLD_BYTES,
        })
        logger.info(
            "  -> Pre-migrate backup skipped (DB size %.1f MB > threshold %.0f MB). "
            "Migrations are idempotent; restart will retry on failure.",
            db_size / 1048576,
            _BACKUP_SKIP_THRESHOLD_BYTES / 1048576,
        )
        return

    reusable_backup = _find_reusable_pre_migrate_backup(db_path, current_version)
    if reusable_backup is not None:
        set_startup_status({
            "kind": "migration",
            "stage": "backup_reused",
            "from_version": current_version,
            "backup_file": reusable_backup.name,
        })
        logger.info("  -> Reusing existing pre-migrate backup: %s", reusable_backup.name)
        return

    # Try new backup system first
    try:
        set_startup_status({
            "kind": "migration",
            "stage": "backup",
            "from_version": current_version,
        })
        t0 = time.perf_counter()
        from importlib import import_module
        _backup_mod = import_module("extensions.builtin_backup.core_impl")
        create_backup = _backup_mod.create_backup
        result = create_backup(db_path=db_path, reason="pre_migrate")
        if result.get("success"):
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            logger.info(f"  -> Backup created: {result['filename']} ({elapsed_ms} ms)")
            return
        logger.warning("New backup system failed: %s", result.get("error"))
    except Exception as exc:
        logger.debug("New backup system unavailable: %s", exc)

    # Fallback to legacy shutil.copy2
    try:
        set_startup_status({
            "kind": "migration",
            "stage": "backup",
            "from_version": current_version,
        })
        t0 = time.perf_counter()
        backup_path = db_path.with_suffix(f".pre_migrate_v{current_version}.bak")
        if backup_path.exists():
            logger.debug("Backup already exists: %s", backup_path)
            return
        shutil.copy2(str(db_path), str(backup_path))
        elapsed_ms = round((time.perf_counter() - t0) * 1000)
        logger.info(f"  -> Backup created: {backup_path.name} ({elapsed_ms} ms)")
    except Exception as exc:
        logger.warning("Failed to create pre-migration backup: %s", exc)


def _validate_after_migrate(con: sqlite3.Connection) -> None:
    # integrity_check decrypts every page, so it also catches SQLCipher HMAC
    # failures from torn writes / SD-card corruption that foreign_key_check
    # cannot see. Run it first: if pages are unreadable, FK check will fail
    # spuriously anyway.
    try:
        from .schema_validate import run_integrity_check

        integrity_result = run_integrity_check(con)
    except Exception as exc:
        logger.error("Post-migration integrity_check raised: %s", exc)
        set_startup_status({
            "kind": "migration",
            "stage": "integrity_check_error",
            "error": str(exc),
        })
        integrity_result = ""

    if integrity_result and integrity_result != "ok":
        logger.error(
            "Post-migration integrity_check reported corruption: %s. "
            "Restore data/tags.db from the pre_migrate backup before continuing.",
            integrity_result,
        )
        set_startup_status({
            "kind": "migration",
            "stage": "integrity_check_failed",
            "result": integrity_result,
        })

    try:
        from .schema_validate import run_foreign_key_check

        violations = run_foreign_key_check(con)
    except Exception as exc:
        logger.warning("Post-migration foreign_key_check failed: %s", exc)
        return

    if violations:
        logger.warning(
            "Post-migration foreign_key_check reported %d violation(s); first=%s",
            len(violations),
            violations[0],
        )


def migrate_db(con: sqlite3.Connection) -> None:
    current_version = get_schema_version(con)

    if current_version >= CURRENT_SCHEMA_VERSION:
        return

    # PRAGMA foreign_keys must be set outside any transaction; do it before
    # apply_pending opens BEGIN IMMEDIATE. With FK OFF, INSERTs added by
    # newer migrations (e.g. v68 sweep_axes -> sweeps cascade refs) would
    # not be enforced and bad data could slip through.
    if not con.in_transaction:
        try:
            con.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            logger.warning("Failed to enable foreign_keys before migrate: %s", exc)

    _precheck_file_wd_tags_rebuild_migrations(con, current_version)
    _backup_before_migrate(con, current_version)

    logger.info(f"Database schema: v{current_version} -> v{CURRENT_SCHEMA_VERSION}")
    set_startup_status({
        "kind": "migration",
        "stage": "migrate",
        "from_version": current_version,
        "to_version": CURRENT_SCHEMA_VERSION,
    })

    apply_pending(con, current_version)
    _validate_after_migrate(con)
    logger.info(f"  [OK] Database updated to schema v{CURRENT_SCHEMA_VERSION}")
