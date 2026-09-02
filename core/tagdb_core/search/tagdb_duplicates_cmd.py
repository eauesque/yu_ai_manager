"""Duplicate finder command for legacy tagdb CLI."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.tagdb_core.db_schema.tagdb_db_schema_common import connect_db

from .tagdb_duplicates_cmd_ops import run_hash_duplicate_flow, run_size_duplicate_flow


def cmd_find_duplicates(args) -> None:
    con = connect_db(Path(args.db))

    logger.info("Finding duplicate files...")

    if args.by_hash:
        run_hash_duplicate_flow(con, args)
    elif args.by_size:
        run_size_duplicate_flow(con)

    con.close()
