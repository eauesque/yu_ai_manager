"""Database diagnostics."""

import logging
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3
from core.services_core.db_migrate_encrypt import _is_plaintext

logger = logging.getLogger(__name__)


def check_db(db_path: str) -> None:
    """Validate DB schema/basic integrity and print diagnostics."""
    logger.info(f"\n=== Database Check: {db_path} ===")

    path_obj = Path(db_path)
    if not path_obj.exists():
        logger.error("  File not found")
        return

    size_mb = path_obj.stat().st_size / (1024 * 1024)
    logger.info(f"  Size: {size_mb:.1f} MB")

    # The runtime tags.db is SQLCipher-encrypted; backup / test DBs may be
    # plaintext. Probe the magic header to pick the right open path.
    con = sqlite3.connect(str(db_path))
    if not _is_plaintext(path_obj):
        apply_key(con)
    con.row_factory = sqlite3.Row

    try:
        ver = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        logger.info(f"  Schema version: {ver}")
    except Exception:
        logger.warning("  schema_version table not found")

    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
    expected = {"files", "tags", "file_tags", "templates", "schema_version"}
    missing = expected - set(tables)
    if missing:
        logger.error(f"  Missing tables: {missing}")
    else:
        logger.info(f"  [OK] All required tables present ({len(tables)} tables)")

    file_count = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
    tag_count = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    tmpl_count = con.execute("SELECT COUNT(*) FROM templates").fetchone()[0]
    logger.info(f"  Files: {file_count:,} | Tags: {tag_count:,} | Templates: {tmpl_count:,}")

    logger.info("  meta_source distribution:")
    for row in con.execute(
        "SELECT COALESCE(meta_source,'null') as ms, COUNT(*) as c "
        "FROM files WHERE is_deleted=0 GROUP BY ms ORDER BY c DESC"
    ).fetchall():
        logger.info(f"     {row[0]}: {row[1]:,}")

    orphan_files = con.execute(
        """
        SELECT COUNT(*) FROM files f
        WHERE f.is_deleted=0 AND f.meta_source IS NOT NULL AND f.meta_source != 'unknown'
        AND NOT EXISTS (SELECT 1 FROM templates t WHERE t.file_id = f.id)
        """
    ).fetchone()[0]
    if orphan_files > 0:
        logger.warning(f"  Has metadata but missing template: {orphan_files} files")
    else:
        logger.info("  [OK] Template integrity OK")

    broken_tags = con.execute(
        """
        SELECT tag, COUNT(*) as c FROM tags
        WHERE tag LIKE '%:%%)' OR tag LIKE '%:%%)' OR tag LIKE '%)%'
        GROUP BY tag ORDER BY c DESC LIMIT 10
        """
    ).fetchall()
    if broken_tags:
        logger.warning("  Broken tag candidates:")
        for row in broken_tags:
            logger.info(f"     {row[0]} ({row[1]} entries)")

    indexes = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchall()]
    logger.info(f"  Indexes: {len(indexes)}")

    journal = con.execute("PRAGMA journal_mode").fetchone()[0]
    logger.info(f"  Journal mode: {journal}")

    con.close()
