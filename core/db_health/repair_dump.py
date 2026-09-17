"""Dump/restore DB repair operations."""

import logging
import shutil
import time
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3

logger = logging.getLogger(__name__)

from .integrity import check_db_integrity


def dump_and_restore(db_path: Path, verbose: bool = False) -> bool:
    if verbose:
        logger.info(f"Dump and restore: {db_path}")
    dump_path = db_path.with_suffix(".sql")
    new_db_path = db_path.with_suffix(".db.new")
    try:
        if verbose:
            logger.info(f"  -> Dumping to {dump_path}...")
        con = sqlite3.connect(str(db_path))
        apply_key(con)
        with open(dump_path, "w", encoding="utf-8") as f:
            for line in con.iterdump():
                f.write(f"{line}\n")
        con.close()
        if verbose:
            logger.info("     Dump completed")

        if verbose:
            logger.info(f"  -> Restoring to {new_db_path}...")
        new_con = sqlite3.connect(str(new_db_path))
        apply_key(new_con)
        with open(dump_path, encoding="utf-8") as f:
            new_con.executescript(f.read())
        new_con.close()
        if verbose:
            logger.info("     Restore completed")

        if verbose:
            logger.info("  -> Verifying new database...")
        is_healthy, issues = check_db_integrity(new_db_path, verbose=False)
        if not is_healthy:
            if verbose:
                logger.error(f"     New DB has issues: {issues}")
            return False

        if verbose:
            logger.info("  -> Replacing old database...")
        backup_path = db_path.with_suffix(f".db.corrupt_{int(time.time())}")
        shutil.move(db_path, backup_path)
        shutil.move(new_db_path, db_path)
        dump_path.unlink()
        if verbose:
            logger.info("Database restored successfully")
            logger.info(f"  Corrupt DB saved as: {backup_path}")
        return True
    except Exception as e:
        if verbose:
            logger.error(f"Dump and restore failed: {e}")
        if dump_path.exists():
            dump_path.unlink()
        if new_db_path.exists():
            new_db_path.unlink()
        return False
