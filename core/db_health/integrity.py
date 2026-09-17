"""DB integrity checks."""

import logging
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3

logger = logging.getLogger(__name__)


class DBHealthError(Exception):
    """Database health check error."""


class DBCorruptionError(DBHealthError):
    """Database is corrupted."""


def check_db_integrity(db_path: Path, verbose: bool = False) -> tuple[bool, list[str]]:
    issues = []
    if not db_path.exists():
        return False, ["Database file does not exist"]
    try:
        con = sqlite3.connect(str(db_path))
        apply_key(con)
        if verbose:
            logger.info("  -> Running integrity_check...")
        result = con.execute("PRAGMA integrity_check").fetchall()
        if result[0][0] != "ok":
            issues.append(f"Integrity check failed: {result}")

        if verbose:
            logger.info("  -> Running quick_check...")
        result = con.execute("PRAGMA quick_check").fetchall()
        if result[0][0] != "ok":
            issues.append(f"Quick check failed: {result}")

        if verbose:
            logger.info("  -> Checking foreign keys...")
        result = con.execute("PRAGMA foreign_key_check").fetchall()
        if result:
            issues.append(f"Foreign key violations: {len(result)} found")

        if verbose:
            logger.info("  -> Verifying schema...")
        required_tables = ["files", "tags", "templates", "file_tags", "schema_version"]
        existing_tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for table in required_tables:
            if table not in existing_tables:
                issues.append(f"Missing table: {table}")

        if verbose:
            logger.info("  -> Checking indexes...")
        indexes = con.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        for idx_name, in indexes:
            try:
                con.execute(f"REINDEX {idx_name}")
            except sqlite3.Error as e:
                issues.append(f"Index {idx_name} is corrupt: {e}")
        con.close()
    except sqlite3.DatabaseError as e:
        issues.append(f"Database error: {e}")
        return False, issues
    return len(issues) == 0, issues
