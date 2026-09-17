"""Migration 69: deferred maintenance job queue."""

import logging

from core.services_core.deferred_maintenance_jobs import ensure_deferred_jobs_table

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _set_schema_version_once(con) -> None:
    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1",
        (69,),
    ).fetchone()
    if row is None:
        set_schema_version(con, 69, "Deferred maintenance job queue")


def apply_migration_69(con) -> None:
    logger.info("  -> Migration 69: deferred maintenance jobs")
    ensure_deferred_jobs_table(con)
    _set_schema_version_once(con)
