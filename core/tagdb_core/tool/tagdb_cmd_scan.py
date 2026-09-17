"""CLI scan command — thin wrapper around the WebUI scan engine.

Historically the CLI ran its own scan loop (`legacy_scan*.py` +
`tagdb_core/scan_metadata/`), which lacked the extension dispatch the
WebUI relies on for parsing ComfyUI / NovelAI / A1111 metadata.

The CLI now delegates to ``core.scan.cli_runner.run_scan_cli``, which
boots the same dependency stack as the web server and calls
``run_scan_background``. CLI and WebUI share one engine.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _run_db_health_check(db: Path) -> None:
    if not (db.exists() and db.stat().st_size > 0):
        return

    logger.info("Checking database health...")
    try:
        from db_health import check_and_repair

        if not check_and_repair(db, auto_repair=True, verbose=False):
            logger.warning("Database health check failed. Proceeding anyway...")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Health check error: {e}. Proceeding anyway...")


def cmd_scan(args, load_or_default_config: Callable[[str], dict[str, Any]]) -> None:
    config = load_or_default_config(args.config)
    explicit_compute_hash = bool(getattr(args, "compute_hash", False))
    if explicit_compute_hash:
        config["compute_hash"] = True

    db = Path(args.db)
    _run_db_health_check(db)

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"root not found: {root}")

    if getattr(args, "exts", None):
        # Kept for backward-compat; the unified engine uses SCAN_EXTS from
        # core.scan.runtime_prepare and ignores per-invocation overrides.
        logger.warning("--exts is deprecated and ignored; using built-in SCAN_EXTS")

    if getattr(args, "mark_deleted", False):
        # Same deal: the unified engine always reconciles deletions inside
        # the scanned root, so the explicit flag is now a no-op.
        logger.info("--mark-deleted is now implicit; flag accepted for compatibility")

    from core.scan.cli_runner import run_scan_cli

    rc = run_scan_cli(
        db_path=db,
        root_path=str(root),
        recursive=bool(getattr(args, "recursive", False)),
        force=bool(getattr(args, "force", False)),
        scan_zips=bool(getattr(args, "scan_zips", False)),
        compute_hash_explicit=explicit_compute_hash,
        config=config,
    )
    if rc != 0:
        raise SystemExit(rc)
