"""CLI command dispatch for tagdb_tool."""

import argparse
from typing import Any

from core.configuration.defaults import DEFAULT_CONFIG
from core.roots_core.config import (
    load_config_json as _load_config_json,
)
from core.roots_core.config import (
    save_config_json as _save_config_json,
)
from core.roots_core.manage import (
    cmd_add_root as _cmd_add_root,
)
from core.roots_core.manage import (
    cmd_list_roots as _cmd_list_roots,
)
from core.roots_core.manage import (
    cmd_remove_root as _cmd_remove_root,
)
from core.roots_core.scan_all import cmd_scan_all as _cmd_scan_all
from core.tagdb_core.search.tagdb_duplicates_cmd import cmd_find_duplicates as _cmd_find_duplicates
from core.tagdb_core.search.tagdb_search_cmd import cmd_search as _cmd_search
from core.tagdb_core.search.tagdb_search_config import load_or_default_config as _load_or_default_config
from core.tagdb_core.search.tagdb_search_query import build_tag_filter_sql as _build_tag_filter_sql
from core.tagdb_core.tool.tagdb_cmd_cleanup import cmd_cleanup as _cmd_cleanup_impl
from core.tagdb_core.tool.tagdb_cmd_scan import cmd_scan as _cmd_scan_impl


def load_or_default_config(path: str | None) -> dict[str, Any]:
    return _load_or_default_config(path, DEFAULT_CONFIG)


def cmd_scan(args: argparse.Namespace) -> None:
    _cmd_scan_impl(args, load_or_default_config)


def cmd_cleanup(args: argparse.Namespace) -> None:
    _cmd_cleanup_impl(args, load_or_default_config)


def cmd_find_duplicates(args: argparse.Namespace) -> None:
    _cmd_find_duplicates(args)


def build_tag_filter_sql(q: str | None) -> tuple[str, list[Any]]:
    return _build_tag_filter_sql(q)


def cmd_search(args: argparse.Namespace) -> None:
    _cmd_search(args, DEFAULT_CONFIG)


def load_config_json(config_path: str | None = None) -> dict:
    return _load_config_json(config_path)


def save_config_json(config: dict, config_path: str = "config.json") -> None:
    _save_config_json(config, config_path)


def cmd_scan_all(args: argparse.Namespace) -> None:
    _cmd_scan_all(args, cmd_scan)


def cmd_add_root(args: argparse.Namespace) -> None:
    _cmd_add_root(args)


def cmd_list_roots(args: argparse.Namespace) -> None:
    _cmd_list_roots(args)


def cmd_remove_root(args: argparse.Namespace) -> None:
    _cmd_remove_root(args)


def cmd_db_info(args: argparse.Namespace) -> None:
    from core.tagdb_core.db.tagdb_db_admin import cmd_db_info as _cmd_db_info

    _cmd_db_info(args)


def cmd_init(args: argparse.Namespace) -> None:
    from core.tagdb_core.db.tagdb_db_admin import cmd_init as _cmd_init

    _cmd_init(args, load_or_default_config)
