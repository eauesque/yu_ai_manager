"""Migration 56: Ensure all tables exist (fixes fresh-DB init gap)."""

import logging

from .schema_connect import table_has_column
from .schema_migrate_56_sql import COLUMNS_SQL, TABLES_SQL
from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_56(con) -> None:
    """Create any tables/columns missing from fresh-init databases."""
    logger.info("  -> Migration 56: ensuring all tables and columns exist (fresh-DB gap fix)")
    con.executescript(TABLES_SQL)
    if table_has_column(con, "file_wd_tags", "tag_name"):
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_wd_tags_tag_name "
            "ON file_wd_tags(tag_name)"
        )
    for table, column, col_def in COLUMNS_SQL:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            logger.info("     Added column %s.%s", table, column)
        except Exception:
            logger.warning("step failed", exc_info=True)
    set_schema_version(con, 56, "Ensure all tables/columns exist (fresh-DB init gap fix)")
