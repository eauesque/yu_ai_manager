"""DB admin commands for tagdb CLI."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.tagdb_core.db_schema.tagdb_db_schema_common import connect_db
from core.tagdb_core.db_schema.tagdb_db_schema_init import init_db
from core.tagdb_core.db_schema.tagdb_db_schema_migrate import (
    CURRENT_SCHEMA_VERSION,
    get_schema_version,
    migrate_db,
)


def cmd_db_info(args) -> None:
    """Show database schema and basic stats."""
    con = connect_db(Path(args.db))

    version = get_schema_version(con)
    logger.info(f"Schema Version: v{version}")

    if version < CURRENT_SCHEMA_VERSION:
        logger.warning(f"Update available: v{version} -> v{CURRENT_SCHEMA_VERSION}")
        logger.info("  Run: python tagdb_tool.py init --db tags.db")
    else:
        logger.info("Up to date")

    try:
        rows = con.execute(
            "SELECT version, applied_at, description FROM schema_version ORDER BY version"
        ).fetchall()

        if rows:
            logger.info("Migration History:")
            for ver, ts, desc in rows:
                import datetime as dt

                # Aware-local: renders the same digits as the old naive
                # call (measured), and the operator wants local time.
                date_str = (
                    dt.datetime.fromtimestamp(ts, tz=dt.UTC)
                    .astimezone()
                    .strftime("%Y-%m-%d %H:%M:%S")
                )
                logger.info(f"  v{ver}: {desc} ({date_str})")
    except Exception:
        # The migration history simply does not print, which reads as "there
        # is none" rather than "it could not be read".
        logger.warning("schema migration history was unreadable", exc_info=True)

    file_count = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
    tag_count = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    logger.info("Database Stats:")
    logger.info(f"  Files: {file_count:,}")
    logger.info(f"  Tags: {tag_count:,}")

    zip_count = con.execute("SELECT COUNT(*) FROM files WHERE is_zip_member=1").fetchone()[0]
    if zip_count > 0:
        logger.info(f"  ZIP members: {zip_count:,}")

    con.close()


def cmd_init(args, load_or_default_config) -> None:
    cfg = load_or_default_config(args.config)
    con = connect_db(Path(args.db))
    init_db(con, enable_fts=bool(cfg.get("enable_fts", True)))
    migrate_db(con)
    con.close()
    logger.info("db initialized")
