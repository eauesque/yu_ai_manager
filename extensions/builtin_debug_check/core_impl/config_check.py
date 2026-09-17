"""Config diagnostics."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def check_config() -> None:
    """Validate config.json and print diagnostics."""
    logger.info("\n=== config.json Check ===")
    config_path = Path("config.json")
    if not config_path.exists():
        logger.info("  [!] config.json not found (running with defaults)")
        return

    raw = config_path.read_text(encoding="utf-8")
    try:
        config = json.loads(raw)
        logger.info("  [OK] Parse succeeded")
    except json.JSONDecodeError as e:
        logger.warning(f"  JSON parse error: {e}")
        if "\\U" in raw or "\\h" in raw or "\\w" in raw:
            logger.info("  [Hint] Invalid Windows path escapes detected")
            logger.info("     Auto-fixed on server startup")
        return

    roots = config.get("scan_roots", [])
    logger.info(f"  scan_roots: {len(roots)} entries")
    for i, root in enumerate(roots):
        root_path = root.get("path", "") if isinstance(root, dict) else root
        exists = os.path.exists(root_path)
        is_dir = os.path.isdir(root_path) if exists else False
        status = "[OK]" if is_dir else ("[!] not dir" if exists else "[NG] not found")
        logger.info(f"     [{i}] {status} {repr(root_path)}")
        if isinstance(root_path, str) and (len(root_path) < 5 or root_path.endswith("\\")):
            logger.info("         [!] Path too short or has trailing backslash")

    server = config.get("server", {})
    if server:
        host = server.get("host", "127.0.0.1")
        port = server.get("port", 5000)
        lan = server.get("lan", False)
        pin = "set" if server.get("pin") else "none"
        logger.info(f"  Server: {host}:{port} (LAN={'public' if lan else 'local'}, PIN={pin})")
