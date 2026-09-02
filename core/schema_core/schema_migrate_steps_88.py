"""Schema migration 88: flag scan_roots recovery for upgraders hit by the
stale-read/reorder-overwrite bug fixed in v4.681.6 (write actions could
silently overwrite ``config.json``'s ``scan_roots`` with a stale, possibly
empty, in-memory snapshot). Runs once per database.
"""

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_88(con: sqlite3.Connection) -> None:
    """Write a recovery marker when this checkout's config has no scan_roots.

    Only the marker file is written here -- the actual candidate-root
    computation (a full ``files`` table scan) runs lazily, on request, via
    ``GET /api/scan-roots/recovery-check``, off this migration's own
    connection and transaction.
    """
    logger.info("  -> Migration 88: scan_roots recovery marker")
    try:
        from core.configuration.api import load_config_json
        from core.paths import data_path

        config = load_config_json(None)
        if not config.get("scan_roots"):
            marker = data_path("scan_roots_recovery_pending.json")
            if not marker.exists():
                marker.write_text('{"pending": true}\n', encoding="utf-8")
    except Exception:
        logger.exception("Migration 88: scan_roots recovery marker failed (non-fatal)")

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (88,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 88, "scan_roots recovery marker")
