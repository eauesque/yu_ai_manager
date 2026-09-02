"""DB query helpers for duplicate finding."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

from core.tools.helpers import find_phash_groups


def query_duplicate_rows(con, method: str, threshold: int):
    if method == "hash":
        # LIMIT 201: cap DB cost; caller slices to 200 and uses 201st row to detect truncation.
        return con.execute(
            """
            SELECT hash, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths,
                   GROUP_CONCAT(id, '|||') as ids
            FROM files
            WHERE hash IS NOT NULL AND hash != '' AND is_deleted = 0
            GROUP BY hash
            HAVING count > 1
            ORDER BY count DESC
            LIMIT 201
            """
        ).fetchall()

    if method == "phash":
        try:
            con.execute("SELECT phash FROM files LIMIT 1")
        except Exception:
            try:
                con.execute("ALTER TABLE files ADD COLUMN phash TEXT")
                con.commit()
            except Exception as exc:
                logger.debug("phash column already exists or alter failed: %s", exc)
        if threshold == 0:
            rows = con.execute(
                """
                SELECT phash, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths,
                       GROUP_CONCAT(id, '|||') as ids
                FROM files
                WHERE phash IS NOT NULL AND phash != '' AND is_deleted = 0
                GROUP BY phash
                HAVING count > 1
                ORDER BY count DESC
                LIMIT 201
                """
            ).fetchall()
            groups = []
            for row in rows:
                phash = row["phash"] if hasattr(row, "keys") else row[0]
                count = row["count"] if hasattr(row, "keys") else row[1]
                paths = row["paths"] if hasattr(row, "keys") else row[2]
                ids = row["ids"] if hasattr(row, "keys") else row[3]
                groups.append(
                    {
                        "hash": f"phash_exact_{phash}",
                        "count": count,
                        "files": paths.split("|||") if paths else [],
                        "ids": [int(value) for value in ids.split("|||")] if ids else [],
                        "similarity": "perceptual",
                    }
                )
            return groups
        rows_raw = con.execute(
            """
            SELECT id, path, phash FROM files
            WHERE phash IS NOT NULL AND phash != '' AND is_deleted = 0
            ORDER BY id DESC
            LIMIT 10000
            """
        ).fetchall()
        return find_phash_groups(rows_raw, threshold)

    if method == "size":
        return con.execute(
            """
            SELECT size, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths,
                   GROUP_CONCAT(id, '|||') as ids
            FROM files
            WHERE is_deleted = 0 AND size > 1024
            GROUP BY size
            HAVING count > 1 AND count <= 20
            ORDER BY size DESC
            LIMIT 201
            """
        ).fetchall()

    return None


def build_hash_stats() -> dict[str, Any]:
    hash_stats: dict[str, Any] = {}
    try:
        from core.services_core.db_api import get_raw_db
        con2 = get_raw_db()
        total_files = con2.execute("SELECT COUNT(*) FROM files WHERE is_deleted=0").fetchone()[0]
        with_hash = con2.execute(
            "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NOT NULL AND hash != ''"
        ).fetchone()[0]
        try:
            with_phash = con2.execute(
                "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND phash IS NOT NULL AND phash != ''"
            ).fetchone()[0]
        except Exception:
            with_phash = 0
        hash_stats = {"total_files": total_files, "with_hash": with_hash, "with_phash": with_phash}
    except Exception as exc:
        logger.debug("Failed to build hash stats: %s", exc)
    return hash_stats
