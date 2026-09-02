"""Add/list/remove scan-roots command implementations."""

import argparse
import logging
import os

logger = logging.getLogger(__name__)

from core.roots_core.config import load_config_json, save_config_json


def cmd_add_root(args: argparse.Namespace) -> None:
    config = load_config_json(args.config)

    if "scan_roots" not in config:
        config["scan_roots"] = []

    path = os.path.abspath(args.path)
    for root in config["scan_roots"]:
        if os.path.abspath(root["path"]) == path:
            logger.warning(f"Path already exists in config: {path}")
            return

    new_root = {
        "path": args.path,
        "enabled": args.enabled,
        "recursive": args.recursive,
        "comment": args.comment,
    }
    config["scan_roots"].append(new_root)

    config_path = args.config if hasattr(args, "config") and args.config else None
    save_config_json(config, config_path)

    logger.info(f"Added root: {args.path}")
    logger.info(f"  Recursive: {args.recursive}")
    logger.info(f"  Enabled: {args.enabled}")
    if args.comment:
        logger.info(f"  Comment: {args.comment}")


def cmd_list_roots(args: argparse.Namespace) -> None:
    config = load_config_json(args.config if hasattr(args, "config") else None)
    roots = config.get("scan_roots", [])

    if not roots:
        logger.info("No scan roots configured.")
        logger.info("Use 'add-root' command to add directories.")
        return

    logger.info(f"=== {len(roots)} Scan Root(s) ===")

    for i, root in enumerate(roots, 1):
        status = "+" if root.get("enabled", True) else "-"
        recursive = "R" if root.get("recursive", True) else " "

        logger.info(f"[{i}] {status} {recursive} {root['path']}")

        if root.get("comment"):
            logger.info(f"      Comment: {root['comment']}")

        if not os.path.exists(root["path"]):
            logger.warning(f"      Path does not exist: {root['path']}")


def cmd_remove_root(args: argparse.Namespace) -> None:
    config = load_config_json(args.config if hasattr(args, "config") else None)

    if "scan_roots" not in config:
        config["scan_roots"] = []

    path = os.path.abspath(args.path)
    original_count = len(config["scan_roots"])

    config["scan_roots"] = [root for root in config["scan_roots"] if os.path.abspath(root["path"]) != path]

    if len(config["scan_roots"]) == original_count:
        logger.warning(f"Path not found in config: {args.path}")
        return

    config_path = args.config if hasattr(args, "config") and args.config else None
    save_config_json(config, config_path)

    logger.info(f"Removed root: {args.path}")
