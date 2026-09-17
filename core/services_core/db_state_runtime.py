"""Runtime guards and once-only setup for DB connections."""

import logging
import threading

from core.services_core.app_runtime_state import get_db_path, get_vectors_db_path
from core.services_core.db_cipher import apply_key, sqlite3

logger = logging.getLogger(__name__)
_cipher_migration_lock = threading.Lock()
_vectors_ready_lock = threading.Lock()


def ensure_vectors_db_ready() -> None:
    from core.services_core import db_state as facade

    vectors_path = str(get_vectors_db_path().resolve())
    if facade._vectors_ready_done and facade._vectors_ready_path == vectors_path:
        return
    with _vectors_ready_lock:
        if facade._vectors_ready_done and facade._vectors_ready_path == vectors_path:
            return
        facade._vectors_ready_done = True
        facade._vectors_ready_path = vectors_path
        try:
            path = get_vectors_db_path()
            con = sqlite3.connect(str(path), timeout=10.0)
            apply_key(con)
            con.execute("""
                CREATE TABLE IF NOT EXISTS file_vectors (
                    file_id    INTEGER PRIMARY KEY,
                    model      TEXT    NOT NULL DEFAULT 'clip_vit_b_16',
                    vector     BLOB    NOT NULL,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_vectors_model"
                " ON file_vectors(model)"
            )
            con.commit()
            con.close()
        except Exception:
            logger.warning(
                "vectors.db init failed — connections may lack file_vectors schema",
                exc_info=True,
            )


def ensure_db_migrated() -> None:
    from core.services_core import db_state as facade

    db_path = str(get_db_path().resolve())
    if facade._cipher_migration_done and facade._cipher_migration_path == db_path:
        return
    with _cipher_migration_lock:
        if facade._cipher_migration_done and facade._cipher_migration_path == db_path:
            return
        facade._cipher_migration_done = True
        facade._cipher_migration_path = db_path
        try:
            from core.services_core.db_migrate_encrypt import migrate_plaintext_to_cipher

            migrate_plaintext_to_cipher(get_db_path())
        except Exception:
            logger.warning("DB cipher migration failed (non-fatal)", exc_info=True)
