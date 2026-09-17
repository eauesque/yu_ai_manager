"""CLI parser construction."""

import argparse

from cli.parser_core.commands_misc import register_misc_commands
from cli.parser_core.commands_roots import register_root_commands
from cli.parser_core.commands_scan import register_scan_commands


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tagdb_tool", add_help=True)
    p.add_argument("--config", help="path to config.json (checkbox flags)", default=None)

    sub = p.add_subparsers(dest="cmd")
    register_misc_commands(sub)
    register_scan_commands(sub)
    register_root_commands(sub)

    return p
