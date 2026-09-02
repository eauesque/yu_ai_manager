"""CLI runtime helpers for tagdb."""

import argparse
import os
from collections.abc import Sequence


def run_main(argv: Sequence[str], parser: argparse.ArgumentParser) -> int:
    if len(argv) == 0:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)

    if args.debug_log is not None:
        os.environ["TAGDB_DEBUG"] = "1" if args.debug_log == "on" else "0"
    if args.debug_log_file is not None:
        os.environ["TAGDB_DEBUG_LOG"] = str(args.debug_log_file)
    if args.debug_log_max_mb is not None:
        os.environ["TAGDB_DEBUG_LOG_MAX_MB"] = str(args.debug_log_max_mb)
    if args.debug_log_backups is not None:
        os.environ["TAGDB_DEBUG_LOG_BACKUPS"] = str(args.debug_log_backups)
    if args.debug_log_stdout is not None:
        os.environ["TAGDB_DEBUG_STDOUT"] = "1" if args.debug_log_stdout == "on" else "0"

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        return 130
