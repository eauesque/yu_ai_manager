"""Operations for legacy duplicate finder CLI command."""

import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


def run_hash_duplicate_flow(con, args) -> None:
    logger.info("Method: Content hash")
    cross_dir_only = getattr(args, "cross_directory", False)

    sql = """
    SELECT hash, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths
    FROM files
    WHERE hash IS NOT NULL AND hash != '' AND is_deleted = 0
    GROUP BY hash
    HAVING count > 1
    ORDER BY count DESC
    """

    rows = con.execute(sql).fetchall()

    if cross_dir_only:
        logger.info("Filter: Cross-directory duplicates only")
        filtered_rows = []
        for hash_val, count, paths in rows:
            path_list = paths.split("|||")
            dirs = set(str(Path(p).parent) for p in path_list)
            if len(dirs) > 1:
                filtered_rows.append((hash_val, count, paths))
        rows = filtered_rows

    if not rows:
        if cross_dir_only:
            logger.info("[OK] No cross-directory duplicates found")
        else:
            logger.info("[OK] No duplicates found (by hash)")
        return

    total_dupes = sum(row[1] - 1 for row in rows)
    logger.info(f"Found {len(rows)} groups with {total_dupes} duplicate files")
    logger.info()

    for hash_val, count, paths in rows:
        path_list = paths.split("|||")

        if cross_dir_only:
            by_dir = defaultdict(list)
            for p in path_list:
                by_dir[str(Path(p).parent)].append(p)

            logger.info(f"Hash: {hash_val[:16]}... ({count} files in {len(by_dir)} directories)")
            for dir_path, files in by_dir.items():
                logger.info(f"  {dir_path}")
                for file_path in files:
                    filename = Path(file_path).name
                    logger.info(f"     - {filename}")
            logger.info()
        else:
            logger.info(f"Hash: {hash_val[:16]}... ({count} files)")
            for i, path in enumerate(path_list, 1):
                size_marker = "  [KEEP]" if i == 1 else "  [DUPE]"
                logger.info(f"  {i}. {path}{size_marker}")
            logger.info()

    if getattr(args, "delete", False):
        logger.info("Deleting duplicates (keeping first occurrence)...")
        deleted = 0
        for _hash_val, _count, paths in rows:
            path_list = paths.split("|||")
            for path in path_list[1:]:
                con.execute("UPDATE files SET is_deleted=1 WHERE path=?", (path,))
                deleted += 1
                logger.info(f"  Marked as deleted: {path}")

        con.commit()
        logger.info(f"\n[OK] Marked {deleted} duplicates as deleted")


def run_size_duplicate_flow(con) -> None:
    logger.info("Method: File size")
    sql = """
    SELECT size, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths
    FROM files
    WHERE is_deleted = 0 AND size > 0
    GROUP BY size
    HAVING count > 1
    ORDER BY count DESC
    LIMIT 100
    """

    rows = con.execute(sql).fetchall()

    if not rows:
        logger.info("[OK] No duplicates found (by size)")
        return

    logger.info(f"Found {len(rows)} size groups (potential duplicates)")
    logger.info("[!] Same size doesn't guarantee duplicates - verify manually")
    logger.info()

    for size, count, paths in rows[:20]:
        path_list = paths.split("|||")
        logger.info(f"Size: {size/1024:.1f} KB ({count} files)")
        for i, path in enumerate(path_list[:5], 1):
            logger.info(f"  {i}. {path}")
        if len(path_list) > 5:
            logger.info(f"  ... and {len(path_list)-5} more")
        logger.info()
