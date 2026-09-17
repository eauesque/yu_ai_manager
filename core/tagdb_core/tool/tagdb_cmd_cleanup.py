"""CLI cleanup command implementation for tagdb."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.cleanup_core.cleanup_files import cleanup_dedupe_paths, cleanup_mark_missing_files, cleanup_prune_unused_tags
from core.cleanup_core.cleanup_tag_merge import cleanup_normalize_tags
from core.scan_core.progress import CLIProgressCallback
from core.tagdb_core.db_schema.tagdb_db_schema_common import connect_db
from core.tagdb_core.db_schema.tagdb_db_schema_init import init_db
from core.tagdb_core.db_schema.tagdb_db_schema_migrate import migrate_db


def cmd_cleanup(args, load_or_default_config: Callable[[str], dict[str, Any]]) -> None:
    cfg = load_or_default_config(args.config)
    con = connect_db(Path(args.db))
    init_db(con, enable_fts=bool(cfg.get("enable_fts", True)))
    migrate_db(con)

    progress = CLIProgressCallback()
    con.execute("BEGIN")

    n_dedupe = 0
    n_tags = 0
    n_missing = 0
    n_normalized = 0

    if args.dedupe_paths:
        progress.on_phase("Deduplicating paths")
        n_dedupe = cleanup_dedupe_paths(con, dry_run=args.dry_run)
        logger.info(f"  -> Removed {n_dedupe} duplicates")

    if args.prune_unused_tags:
        progress.on_phase("Pruning unused tags")
        n_tags = cleanup_prune_unused_tags(con, dry_run=args.dry_run)
        logger.info(f"  -> Removed {n_tags} unused tags")

    if args.mark_missing:
        progress.on_phase("Marking missing files")
        n_missing = cleanup_mark_missing_files(con, dry_run=args.dry_run)
        logger.info(f"  -> Marked {n_missing} files as deleted")

    if getattr(args, "normalize_tags", False):
        progress.on_phase("Normalizing tags")
        n_normalized = cleanup_normalize_tags(con, dry_run=args.dry_run)
        logger.info(f"  -> Merged {n_normalized} duplicate tags")

    if args.dry_run:
        con.execute("ROLLBACK")
        logger.warning("Dry-run mode: no changes were committed")
    else:
        con.commit()

    if args.vacuum and (not args.dry_run):
        progress.on_phase("Vacuuming database")
        con.execute("VACUUM")
        logger.info("  -> Database compacted")

    con.close()
    logger.info("Cleanup complete")
