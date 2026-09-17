"""Automatic DB repair operations (VACUUM/REINDEX/ANALYZE)."""

import logging
import shutil
import time
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3

logger = logging.getLogger(__name__)

from .integrity import check_db_integrity


def auto_repair_db(db_path: Path, backup: bool = True, verbose: bool = False) -> bool:
    if verbose:
        logger.info(f"Auto-repairing database: {db_path}")
    if backup:
        backup_path = db_path.with_suffix(f".db.backup_{int(time.time())}")
        if verbose:
            logger.info(f"  -> Creating backup: {backup_path}")
        shutil.copy2(db_path, backup_path)
    try:
        con = sqlite3.connect(str(db_path))
        apply_key(con)
        if verbose:
            logger.info("  -> Running VACUUM...")
        try:
            con.execute("VACUUM")
            if verbose:
                logger.info("     [OK] VACUUM completed")
        except sqlite3.Error as e:
            if verbose:
                logger.error(f"     VACUUM failed: {e}")

        if verbose:
            logger.info("  -> Rebuilding indexes...")
        try:
            con.execute("REINDEX")
            if verbose:
                logger.info("     [OK] REINDEX completed")
        except sqlite3.Error as e:
            if verbose:
                logger.error(f"     REINDEX failed: {e}")

        if verbose:
            logger.info("  -> Updating statistics...")
        try:
            con.execute("ANALYZE")
            if verbose:
                logger.info("     [OK] ANALYZE completed")
        except sqlite3.Error as e:
            if verbose:
                logger.error(f"     ANALYZE failed: {e}")
        con.close()

        if verbose:
            logger.info("  -> Verifying repair...")
        is_healthy, issues = check_db_integrity(db_path, verbose=False)
        if is_healthy:
            if verbose:
                logger.info("[OK] Database repaired successfully")
            return True
        if verbose:
            logger.error(f"Repair failed. Issues remain: {issues}")
        return False
    except Exception as e:
        if verbose:
            logger.error(f"Repair failed: {e}")
        return False
