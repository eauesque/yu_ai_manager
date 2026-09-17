"""Database readiness checks and rescan hints for web_ui startup.

Performance optimizations for large databases (100K+ files):
- Uses db_meta cached stats instead of COUNT(*) full scans
- Defers parser version check and FTS health to background thread
- Adds missing index for (is_deleted, parser_version) via migration 49
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from core.schema_core.schema import (
    CURRENT_PARSER_VERSION,
    CURRENT_SCHEMA_VERSION,
    connect_db,
    get_schema_version,
    init_db,
    migrate_db,
    set_schema_version,
)
from core.services_core.db_api import set_startup_migration_info, set_startup_status


def check_db_schema_and_print_rescan(db_path: Path) -> None:
    """Run schema init/migration synchronously, then defer heavy checks."""
    logger.info("Checking database schema...")
    con = connect_db(db_path)

    is_fresh = get_schema_version(con) == 0
    # Create base schema (CREATE TABLE IF NOT EXISTS -- no effect on existing DB)
    #
    # enable_fts=True is deliberately hardcoded and must stay that way: the
    # config key of that name applies to the CLI tools (core/scan/runtime_prepare.py,
    # core/tagdb_core/tool/, core/tagdb_core/search/), not to the server. Search
    # MATCHes the FTS5 virtual tables directly -- crates/yu-server/src/routes/search.rs
    # queries templates_fts -- so a server database without them fails at runtime,
    # not gracefully. The Rust genesis SQL bakes FTS in for the same reason.
    # tests/test_enable_fts_semantics.py pins this.
    init_db(con, enable_fts=True)

    if is_fresh:
        # Fresh DB: BASE_SCHEMA_SQL already created the latest tables
        # Set version to latest to skip all migrations
        set_schema_version(con, CURRENT_SCHEMA_VERSION, "Fresh database init")
        con.commit()
        logger.info("  [OK] New database initialized at schema v%d", CURRENT_SCHEMA_VERSION)
        set_startup_migration_info(None)
        set_startup_status(None)
    else:
        before_version = get_schema_version(con)
        if before_version < CURRENT_SCHEMA_VERSION:
            set_startup_status({
                "kind": "migration",
                "stage": "prepare",
                "from_version": before_version,
                "to_version": CURRENT_SCHEMA_VERSION,
            })
            t0 = time.perf_counter()
            migrate_db(con)
            elapsed_ms = round((time.perf_counter() - t0) * 1000)
            set_startup_migration_info({
                "from_version": before_version,
                "to_version": CURRENT_SCHEMA_VERSION,
                "elapsed_ms": elapsed_ms,
                "message": f"Database schema upgraded from v{before_version} to v{CURRENT_SCHEMA_VERSION} during startup",
            })
            set_startup_status({
                "kind": "migration_done",
                "stage": "done",
                "from_version": before_version,
                "to_version": CURRENT_SCHEMA_VERSION,
                "elapsed_ms": elapsed_ms,
            })
        else:
            set_startup_migration_info(None)
            set_startup_status(None)

    con.close()
    logger.info("  [OK] Database ready (deferred checks in background)")

    # Run expensive checks in background to avoid blocking startup
    threading.Thread(
        target=_deferred_db_checks,
        args=(db_path,),
        name="startup-db-checks",
        daemon=True,
    ).start()


def _deferred_db_checks(db_path: Path) -> None:
    """Run parser version check and FTS health in background."""
    try:
        con = connect_db(db_path)
        _check_parser_version(con)
        _check_fts_health(con)
        con.close()
    except Exception as exc:
        logger.debug("Deferred DB checks failed: %s", exc)


def _check_parser_version(con) -> None:
    """Check parser version stats using db_meta cache first."""
    rescan_reason = []
    try:
        # Try cached stats from db_meta first (instant)
        total_files = None
        old_parser_count = None
        try:
            from core.services_core.db_meta import get_meta_int
            total_files = get_meta_int(con, "total_files", -1)
            old_parser_count = get_meta_int(con, "old_parser_count", -1)
        except Exception:
            # Falls back to COUNT(*) below, which is correct but slow on every
            # startup -- worth knowing it has been happening.
            logger.warning("db_meta counters were unreadable", exc_info=True)

        if total_files is None or total_files < 0:
            # db_meta not populated yet; fall back to COUNT
            # This uses the new idx_files_deleted_parser_version index
            old_parser_count = con.execute(
                "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND parser_version < ?",
                (CURRENT_PARSER_VERSION,),
            ).fetchone()[0]
            total_files = con.execute(
                "SELECT COUNT(*) FROM files WHERE is_deleted=0"
            ).fetchone()[0]

            # Populate db_meta for next startup
            try:
                from core.services_core.db_meta import set_meta
                set_meta(con, "total_files", str(total_files))
                set_meta(con, "old_parser_count", str(old_parser_count))
                con.commit()
            except Exception:
                # The cache this populates is why the next startup skips the
                # COUNT. Failing silently means it never gets faster.
                logger.warning("db_meta counters were not persisted", exc_info=True)

        if total_files > 0 and old_parser_count > 0:
            percent = (old_parser_count / total_files) * 100
            if percent >= 5:
                rescan_reason.append(
                    f"{old_parser_count:,} / {total_files:,} files ({percent:.1f}%) at older parser version"
                )
                rescan_reason.append(
                    f"  -> Current parser: v{CURRENT_PARSER_VERSION}"
                )
    except Exception as exc:
        logger.debug("Failed to check parser version stats: %s", exc)

    if not rescan_reason:
        return

    logger.warning("=" * 60)
    logger.warning("  [WARNING] RE-SCAN RECOMMENDED")
    logger.warning("=" * 60)
    for reason in rescan_reason:
        logger.warning(f"  {reason}")
    logger.warning("")
    logger.warning("To update metadata, run scan-all from Tools page")
    logger.warning("or: python tagdb_tool.py scan --db %s --root <path> --recursive", con.execute("PRAGMA database_list").fetchone()[2] or "data/tags.db")
    logger.warning("")
    logger.warning("Note: Only changed files will be re-parsed (fast!)")
    logger.warning("=" * 60)


def _check_fts_health(con) -> None:
    """FTS5 files_path_fts health check (deferred)."""
    try:
        fts_exists = False
        try:
            con.execute("SELECT 1 FROM files_path_fts LIMIT 0")
            fts_exists = True
        except sqlite3.Error:
            # A probe: the exception IS the answer (no FTS table yet).
            pass
        if not fts_exists:
            return

        # Use db_meta for total count if available
        total = None
        try:
            from core.services_core.db_meta import get_meta_int
            total = get_meta_int(con, "total_files", -1)
        except Exception:
            logger.warning("db_meta total_files was unreadable", exc_info=True)
        if total is None or total < 0:
            total = con.execute(
                "SELECT COUNT(*) FROM files WHERE is_deleted=0"
            ).fetchone()[0]
        if total == 0:
            return

        # Verify FTS returns results for a sample file path
        sample = con.execute(
            "SELECT path FROM files WHERE is_deleted=0 AND path IS NOT NULL AND path != '' LIMIT 1"
        ).fetchone()
        needs_rebuild = False
        if sample:
            import os
            basename = os.path.basename(sample["path"])
            if basename:
                fts_count = con.execute(
                    "SELECT COUNT(*) FROM files_path_fts WHERE files_path_fts MATCH ?",
                    (f'"{basename}"',),
                ).fetchone()[0]
                if fts_count == 0:
                    needs_rebuild = True
                    logger.warning("  [FTS] Index appears stale (sample '%s' not found)", basename)
        else:
            needs_rebuild = True

        if needs_rebuild:
            con.execute(
                "INSERT INTO files_path_fts(files_path_fts) VALUES('rebuild')"
            )
            con.commit()
            logger.info("  [FTS] files_path_fts rebuilt (%d files)", total)
        else:
            logger.info("  [FTS] files_path_fts OK (skipped rebuild)")
    except Exception as exc:
        logger.debug("FTS health check skipped: %s", exc)
