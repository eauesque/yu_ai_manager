"""Migration 64: Switch FTS5 tables to trigram tokenizer for CJK support.

The previous ``unicode61`` tokenizer treats CJK runs (e.g. ``日本語``) as a
single token. Prefix queries like ``MATCH '"日本語"*'`` then become a full
virtual-table scan because the FTS index has no shorter tokens to seek on.
EXPLAIN QUERY PLAN confirms ``SCAN files_path_fts VIRTUAL TABLE INDEX 0:M0``
on dev DB, which translates to multi-second scans on production.

The ``trigram`` tokenizer (SQLite >= 3.34) indexes every 3-character window,
so substring queries — including CJK — become real index seeks. It also
transparently accelerates ``LIKE '%substring%'`` on the FTS column. ASCII
queries continue to work via the same ``MATCH``/``LIKE`` syntax.

Storage cost: trigram indexes are ~30-50% larger than unicode61 because
they store every 3-char window. Acceptable trade-off for sub-second CJK
search vs the prior 9-13s cold path.

Migration steps for each affected FTS table:
  1. Snapshot column list (``templates_fts`` may or may not have the
     ``char_positive``/``char_negative`` columns depending on prior
     migrations).
  2. Drop existing triggers + virtual table.
  3. Recreate as ``USING fts5(... tokenize='trigram')``.
  4. Repopulate from base table via INSERT INTO ... SELECT.
  5. Recreate triggers.

This is one-time O(N) per affected table; large prod DBs may see a
multi-minute startup pause once. Subsequent restarts are fast.
"""

import contextlib
import logging

from core.services_core.db_api import set_startup_status

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _set_rebuild_stage(table: str) -> None:
    """Surface a frontend-friendly stage so the boot banner shows a specific
    'Rebuilding search indexes' message instead of the generic 'migrate'.

    Errors are swallowed because this is purely cosmetic — the migration
    itself must not fail because of a status-display failure.
    """
    with contextlib.suppress(Exception):
        set_startup_status({
            "kind": "migration",
            "stage": "rebuild_fts",
            "to_version": 64,
            "table": table,
        })


def _table_columns(con, table: str) -> list[str]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
    return [row[1] for row in rows]


def _drop_triggers(con, prefix_or_names: list[str]) -> None:
    for name in prefix_or_names:
        con.execute(f"DROP TRIGGER IF EXISTS {name}")


def _migrate_files_path_fts(con) -> None:
    cols = _table_columns(con, "files_path_fts")
    if not cols:
        logger.info("    files_path_fts not present, creating fresh trigram FTS")
        con.execute(
            "CREATE VIRTUAL TABLE files_path_fts USING fts5("
            "path, content='files', content_rowid='id', tokenize='trigram')"
        )
    else:
        logger.info("    rebuilding files_path_fts with trigram tokenizer")
        _drop_triggers(con, ["files_path_fts_ai", "files_path_fts_au", "files_path_fts_ad"])
        con.execute("DROP TABLE IF EXISTS files_path_fts")
        con.execute(
            "CREATE VIRTUAL TABLE files_path_fts USING fts5("
            "path, content='files', content_rowid='id', tokenize='trigram')"
        )
    _set_rebuild_stage("files_path_fts")
    con.execute(
        "INSERT INTO files_path_fts(rowid, path) "
        "SELECT id, path FROM files WHERE path IS NOT NULL"
    )
    con.execute(
        "CREATE TRIGGER IF NOT EXISTS files_path_fts_ai "
        "AFTER INSERT ON files BEGIN "
        "  INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path); "
        "END"
    )
    con.execute(
        "CREATE TRIGGER IF NOT EXISTS files_path_fts_ad "
        "AFTER DELETE ON files BEGIN "
        "  INSERT INTO files_path_fts(files_path_fts, rowid, path) "
        "  VALUES ('delete', old.id, old.path); "
        "END"
    )
    con.execute(
        "CREATE TRIGGER IF NOT EXISTS files_path_fts_au "
        "AFTER UPDATE OF path ON files BEGIN "
        "  INSERT INTO files_path_fts(files_path_fts, rowid, path) "
        "  VALUES ('delete', old.id, old.path); "
        "  INSERT INTO files_path_fts(rowid, path) VALUES (new.id, new.path); "
        "END"
    )


def _migrate_templates_fts(con) -> None:
    existing_cols = _table_columns(con, "templates_fts")
    base_cols = _table_columns(con, "templates")
    if not existing_cols and not base_cols:
        logger.info("    templates table not present yet — skipping templates_fts")
        return
    fts_cols = ["raw_prompt", "raw_negative"]
    if "char_positive" in base_cols:
        fts_cols.append("char_positive")
    if "char_negative" in base_cols:
        fts_cols.append("char_negative")
    fts_cols_sql = ", ".join(fts_cols)

    if existing_cols:
        logger.info("    rebuilding templates_fts with trigram tokenizer")
        _drop_triggers(con, ["templates_ai", "templates_au", "templates_ad"])
        con.execute("DROP TABLE IF EXISTS templates_fts")
    else:
        logger.info("    creating templates_fts with trigram tokenizer")

    con.execute(
        f"CREATE VIRTUAL TABLE templates_fts USING fts5("  # noqa: S608
        f"{fts_cols_sql}, content='templates', content_rowid='id', tokenize='trigram')"
    )
    _set_rebuild_stage("templates_fts")
    con.execute(
        f"INSERT INTO templates_fts(rowid, {fts_cols_sql}) "  # noqa: S608
        f"SELECT id, {fts_cols_sql} FROM templates"
    )
    new_set = ", ".join(f"new.{c}" for c in fts_cols)
    old_set = ", ".join(f"old.{c}" for c in fts_cols)
    con.execute(
        f"CREATE TRIGGER IF NOT EXISTS templates_ai AFTER INSERT ON templates BEGIN "  # noqa: S608
        f"  INSERT INTO templates_fts(rowid, {fts_cols_sql}) "
        f"  VALUES (new.id, {new_set}); "
        f"END"
    )
    con.execute(
        f"CREATE TRIGGER IF NOT EXISTS templates_ad AFTER DELETE ON templates BEGIN "  # noqa: S608
        f"  INSERT INTO templates_fts(templates_fts, rowid, {fts_cols_sql}) "
        f"  VALUES ('delete', old.id, {old_set}); "
        f"END"
    )
    con.execute(
        f"CREATE TRIGGER IF NOT EXISTS templates_au AFTER UPDATE ON templates BEGIN "  # noqa: S608
        f"  INSERT INTO templates_fts(templates_fts, rowid, {fts_cols_sql}) "
        f"  VALUES ('delete', old.id, {old_set}); "
        f"  INSERT INTO templates_fts(rowid, {fts_cols_sql}) "
        f"  VALUES (new.id, {new_set}); "
        f"END"
    )


_MIN_SQLITE_VERSION = (3, 34, 0)


def _check_sqlite_supports_trigram(con) -> tuple[bool, str]:
    """Trigram tokenizer requires SQLite >= 3.34.0 (2020-12-01).

    Older builds raise ``no such tokenizer: trigram`` mid-migration, leaving
    the FTS table dropped. Check upfront and skip the migration on incompatible
    builds rather than failing startup.
    """
    row = con.execute("SELECT sqlite_version()").fetchone()
    raw = (row[0] if row else "0.0.0") or "0.0.0"
    try:
        ver = tuple(int(x) for x in raw.split(".")[:3])
    except (ValueError, AttributeError):
        return False, raw
    return ver >= _MIN_SQLITE_VERSION, raw


def apply_migration_64(con) -> None:
    logger.info("  -> Migration 64: switch FTS5 tables to trigram tokenizer (CJK fix)")
    ok, ver = _check_sqlite_supports_trigram(con)
    if not ok:
        logger.warning(
            "    SQLite %s is older than %s; skipping trigram migration "
            "(CJK search will use LIKE fallback). Upgrade sqlcipher3/SQLite to enable.",
            ver, ".".join(str(x) for x in _MIN_SQLITE_VERSION),
        )
        set_schema_version(
            con, 64,
            f"Trigram migration skipped: SQLite {ver} < required "
            f"{'.'.join(str(x) for x in _MIN_SQLITE_VERSION)}",
        )
        return

    _migrate_files_path_fts(con)
    _migrate_templates_fts(con)
    # Set version in the same transaction as the FTS rebuild so a crash between
    # them can't leave a rebuilt FTS with version still at 63 (would re-run
    # the multi-minute INSERT on every restart).
    set_schema_version(
        con, 64, "Switch files_path_fts and templates_fts to trigram tokenizer for CJK support"
    )

    # Migration 64 may have just created files_path_fts where it was missing
    # before; invalidate the path-fts availability cache so the running process
    # picks it up without a restart.
    try:
        from core.query.filters_common_date_path import invalidate_fts_available_cache
        invalidate_fts_available_cache()
    except Exception:  # pragma: no cover - defensive only
        logger.debug("could not invalidate path FTS cache", exc_info=True)
