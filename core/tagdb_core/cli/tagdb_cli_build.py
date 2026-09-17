"""CLI parser builder for tagdb."""

import argparse
from collections.abc import Callable

from core.tagdb_core.cli.tagdb_cli_examples import legacy_cli_examples
from core.tagdb_core.cli.tagdb_cli_subcommands import register_subcommands


def build_parser(handlers: dict[str, Callable]) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tagdb_tool",
        description="YU AI Manager CLI — AI生成画像のメタデータ管理ツール。スキャン・検索・クリーンアップ等をCLIから実行。",
        epilog=legacy_cli_examples(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    p.add_argument("--config", help="path to config.json (checkbox flags)", default=None)
    p.add_argument("--debug-log", choices=("on", "off"), help="structured debug log on/off (same as TAGDB_DEBUG=1/0)")
    p.add_argument("--debug-log-file", help="debug log file path (same as TAGDB_DEBUG_LOG)")
    p.add_argument("--debug-log-max-mb", type=int, help="debug log max size in MB (same as TAGDB_DEBUG_LOG_MAX_MB)")
    p.add_argument("--debug-log-backups", type=int, help="debug log backup generations (same as TAGDB_DEBUG_LOG_BACKUPS)")
    p.add_argument("--debug-log-stdout", choices=("on", "off"), help="debug log stdout on/off (same as TAGDB_DEBUG_STDOUT=1/0)")

    sub = p.add_subparsers(dest="cmd")
    register_subcommands(sub, handlers)
    return p
