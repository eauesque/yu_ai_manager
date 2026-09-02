"""CLI parser/main entry for tagdb_tool."""

from collections.abc import Sequence

from .tagdb_tool_commands import (
    cmd_add_root,
    cmd_cleanup,
    cmd_db_info,
    cmd_find_duplicates,
    cmd_init,
    cmd_list_roots,
    cmd_remove_root,
    cmd_scan,
    cmd_scan_all,
    cmd_search,
)


def build_parser():
    from core.tagdb_core.cli.tagdb_cli_build import build_parser as _build_parser

    return _build_parser(
        {
            "cmd_db_info": cmd_db_info,
            "cmd_init": cmd_init,
            "cmd_scan": cmd_scan,
            "cmd_scan_all": cmd_scan_all,
            "cmd_add_root": cmd_add_root,
            "cmd_list_roots": cmd_list_roots,
            "cmd_remove_root": cmd_remove_root,
            "cmd_search": cmd_search,
            "cmd_cleanup": cmd_cleanup,
            "cmd_find_duplicates": cmd_find_duplicates,
        }
    )


def main(argv: Sequence[str]) -> int:
    from core.tagdb_core.cli.tagdb_cli_run import run_main as _run_main

    parser = build_parser()
    return _run_main(argv, parser)
