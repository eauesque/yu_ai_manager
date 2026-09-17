"""CLI entry runner for debug diagnostics."""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)

from .config_check import check_config
from .db_check import check_db
from .extensions_check import check_extensions
from .modules_check import check_modules
from .syntax_check import check_syntax


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YU AI Manager Debug Diagnostics")
    parser.add_argument("--db", default="tags.db", help="Database path")
    parser.add_argument("--quick", action="store_true", help="Quick check only")
    return parser


def run(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logger.info("YU AI Manager Debug Diagnostics")
    logger.info(f"   Working directory: {os.getcwd()}")
    logger.info(f"   Python: {sys.version}")

    check_config()
    check_db(args.db)

    if not args.quick:
        check_extensions()
        check_modules()
        check_syntax()

    logger.info("=== Done ===")
    return 0
