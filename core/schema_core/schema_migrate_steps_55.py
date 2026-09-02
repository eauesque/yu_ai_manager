"""Migration 55: Move file_vectors from tags.db to vectors.db (float16)."""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version

_CHUNK_SIZE = 10_000


def _resolve_vectors_db_path(con) -> Path:
    from core.services_core.app_runtime_state import get_db_path

    try:
        return get_db_path().parent / "vectors.db"
    except RuntimeError:
        rows = con.execute("PRAGMA database_list").fetchall()
        for row in rows:
            if len(row) >= 3 and row[1] == "main" and row[2]:
                return Path(row[2]).resolve().parent / "vectors.db"
    temp_dir = Path(tempfile.mkdtemp(prefix="yuai-vectors-migration-"))
    return temp_dir / "vectors.db"


def apply_migration_55(con) -> None:
    """Create vectors.db, migrate file_vectors as float16, drop from tags.db."""
    import numpy as np
    from sqlcipher3 import dbapi2 as cipher_sqlite3

    from core.services_core.db_cipher import apply_key

    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "file_vectors" not in tables:
        logger.info("  -> Migration 55: file_vectors not in tags.db, skipping data move")
        set_schema_version(con, 55, "file_vectors moved to vectors.db (float16)")
        return

    vectors_db_path = _resolve_vectors_db_path(con)
    logger.info("  -> Migration 55: moving file_vectors -> %s (float16)", vectors_db_path.name)

    # Create / open vectors.db
    vec_con = cipher_sqlite3.connect(str(vectors_db_path), timeout=60.0)
    try:
        apply_key(vec_con)
        vec_con.execute("""
            CREATE TABLE IF NOT EXISTS file_vectors (
                file_id    INTEGER PRIMARY KEY,
                model      TEXT    NOT NULL DEFAULT 'clip_vit_b_16',
                vector     BLOB    NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        vec_con.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model)"
        )
        vec_con.commit()

        # Chunked float32 -> float16 migration
        total = con.execute("SELECT COUNT(*) FROM file_vectors").fetchone()[0]
        logger.info("     Migrating %d vectors in chunks of %d ...", total, _CHUNK_SIZE)

        cursor = con.execute(
            "SELECT file_id, model, vector, created_at FROM file_vectors ORDER BY file_id"
        )
        migrated = 0
        while True:
            chunk = cursor.fetchmany(_CHUNK_SIZE)
            if not chunk:
                break
            converted = [
                (
                    row[0],
                    row[1],
                    np.frombuffer(row[2], dtype=np.float32).astype(np.float16).tobytes(),
                    row[3],
                )
                for row in chunk
            ]
            vec_con.execute("BEGIN IMMEDIATE")
            vec_con.executemany(
                """INSERT INTO file_vectors
                   (file_id, model, vector, created_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                     model=excluded.model,
                     vector=excluded.vector,
                     created_at=excluded.created_at""",
                converted,
            )
            vec_con.commit()
            migrated += len(converted)
            logger.info("     ... %d / %d", migrated, total)

        logger.info("     Migration complete: %d vectors written to vectors.db", migrated)
    finally:
        vec_con.close()

    # Drop from tags.db (within the outer migration transaction)
    con.execute("DROP TABLE file_vectors")
    logger.info("     file_vectors dropped from tags.db")

    set_schema_version(con, 55, "file_vectors moved to vectors.db (float16)")
