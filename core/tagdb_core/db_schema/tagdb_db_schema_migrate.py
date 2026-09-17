"""DB schema migration helpers for legacy tagdb CLI."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .tagdb_db_schema_constants import CURRENT_SCHEMA_VERSION
from .tagdb_db_schema_migrate_steps import (
    apply_migration_1,
    apply_migration_2,
    apply_migration_3,
    apply_migration_4,
    apply_migration_5,
)
from .tagdb_db_schema_migrate_version import get_schema_version


def migrate_db(con: sqlite3.Connection) -> None:
    current_version = get_schema_version(con)
    if current_version >= CURRENT_SCHEMA_VERSION:
        return

    logger.info(f"Database schema: v{current_version} -> v{CURRENT_SCHEMA_VERSION}")

    if current_version < 1:
        apply_migration_1(con)

    if current_version < 2:
        apply_migration_2(con)

    if current_version < 3:
        apply_migration_3(con)

    if current_version < 4:
        apply_migration_4(con)

    if current_version < 5:
        apply_migration_5(con)

    con.commit()
    logger.info(f"Database updated to schema v{CURRENT_SCHEMA_VERSION}")
