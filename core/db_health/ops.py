"""Database health check and repair operations."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from .integrity import DBCorruptionError, DBHealthError, check_db_integrity
from .repair import auto_repair_db, dump_and_restore


def check_and_repair(db_path: Path, auto_repair: bool = True, verbose: bool = False) -> bool:
    if verbose:
        logger.info(f"Checking database health: {db_path}")
    is_healthy, issues = check_db_integrity(db_path, verbose=verbose)
    if is_healthy:
        if verbose:
            logger.info("Database is healthy")
        return True
    if verbose:
        logger.warning(f"Database has {len(issues)} issue(s):")
        for issue in issues:
            logger.warning(f"   - {issue}")
    if not auto_repair:
        return False
    if verbose:
        logger.info("Attempting auto-repair...")
    if auto_repair_db(db_path, backup=True, verbose=verbose):
        return True
    if verbose:
        logger.warning("Level 1 repair failed. Trying Level 2 (dump and restore)...")
    if dump_and_restore(db_path, verbose=verbose):
        return True
    if verbose:
        logger.error("Auto-repair failed. Manual intervention required.")
    return False


__all__ = [
    "DBHealthError",
    "DBCorruptionError",
    "check_db_integrity",
    "auto_repair_db",
    "dump_and_restore",
    "check_and_repair",
]
