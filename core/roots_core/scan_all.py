"""Scan-all command implementation."""

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

from core.roots_core.config import load_config_json


def cmd_scan_all(args: argparse.Namespace, cmd_scan_func: Callable[[argparse.Namespace], None]) -> None:
    config = load_config_json(args.config)
    roots = config.get("scan_roots", [])

    if not roots:
        logger.warning("No scan_roots configured in config.json")
        logger.info("Use 'add-root' command to add directories")
        return

    db_path = Path(args.db)
    logger.info(f"=== Scanning {len(roots)} root(s) ===")

    for i, root_config in enumerate(roots, 1):
        if not root_config.get("enabled", True):
            logger.info(f"[{i}/{len(roots)}] SKIPPED (disabled): {root_config['path']}")
            continue

        path = root_config["path"]
        recursive = root_config.get("recursive", True)
        comment = root_config.get("comment", "")

        logger.info(f"[{i}/{len(roots)}] Scanning: {path}")
        if comment:
            logger.info(f"  Comment: {comment}")
        logger.info(f"  Recursive: {recursive}")

        scan_args = argparse.Namespace(
            db=str(db_path),
            root=path,
            recursive=recursive,
            exts=".png,.jpg,.jpeg,.webp,.webm,.jxl,.avif,.heif,.heic,.svg,.pdf",
            mark_deleted=False,
            force=getattr(args, "force", False),
            scan_zips=getattr(args, "scan_zips", False),
            compute_hash=False,
            config=args.config if hasattr(args, "config") else None,
        )

        try:
            cmd_scan_func(scan_args)
        except Exception as e:
            logger.error(f"Failed to scan {path}: {e}")
            continue

    logger.info("=== Scan complete ===")
