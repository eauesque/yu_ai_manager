"""One-time migration: convert a plaintext SQLite DB to SQLCipher-encrypted."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from sqlcipher3 import dbapi2 as cipher_sqlite3

from core.services_core.db_cipher import _APP_KEY

assert not any(ch in _APP_KEY for ch in ("'", ";", "\\")), (
    "_APP_KEY must remain a controlled SQLCipher key literal"
)

logger = logging.getLogger(__name__)


def _is_encrypted(db_path: Path) -> bool:
    """Return True if the DB is already encrypted with the app key."""
    try:
        con = cipher_sqlite3.connect(str(db_path), timeout=5.0)
        con.execute("PRAGMA cipher_memory_security=OFF")
        # f-string interpolation is safe only while _APP_KEY remains a
        # controlled constant guarded by the module-level assertion above.
        con.execute(f"PRAGMA key='{_APP_KEY}'")
        con.execute("SELECT count(*) FROM sqlite_master")
        con.close()
        return True
    except Exception:
        return False


_SQLITE_MAGIC = b"SQLite format 3\x00"


def _is_plaintext(db_path: Path) -> bool:
    """Return True if the DB is a readable plaintext SQLite file.

    Probes the file header directly instead of opening a SQLCipher
    connection — the previous implementation issued a SELECT without
    PRAGMA key and caused SQLCipher to emit ``hmac check failed for
    pgno=1`` ERROR lines on every encrypted DB, once per worker
    subprocess startup.
    """
    try:
        with db_path.open("rb") as f:
            return f.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def migrate_plaintext_to_cipher(db_path: Path) -> None:
    """Encrypt a plaintext SQLite DB in-place using SQLCipher.

    Creates a .plain_bak backup before replacing. Safe to call multiple times
    (no-op if already encrypted).
    """
    if not db_path.exists():
        return
    if _is_plaintext(db_path):
        pass  # fall through to encryption below
    elif _is_encrypted(db_path):
        # Only probed with the cipher key once the quiet magic-header check
        # above has ruled out plaintext — avoids emitting a SQLCipher
        # "hmac check failed for pgno=1" ERROR line (same noise pattern
        # documented on _is_plaintext) on every ordinary plaintext DB.
        logger.debug("DB already encrypted: %s", db_path)
        return
    else:
        logger.warning("DB is neither plaintext nor encrypted with app key: %s", db_path)
        return

    tmp_path = db_path.with_suffix(".db.encrypting")
    backup_path = db_path.with_suffix(".db.plain_bak")

    # Normalize path separators for SQLCipher ATTACH (Windows backslash causes parse errors)
    tmp_path_str = str(tmp_path).replace("\\", "/")

    logger.info("Encrypting DB: %s -> SQLCipher ...", db_path.name)
    try:
        # Open plaintext DB via cipher with plaintext header hint
        src = cipher_sqlite3.connect(str(db_path), timeout=60.0)
        src.execute("PRAGMA cipher_plaintext_header_size = 32")

        # Export to new encrypted file via ATTACH
        # f-string interpolation is safe here because tmp_path_str is a
        # generated path and _APP_KEY is guarded as a controlled literal.
        src.execute(f"ATTACH DATABASE '{tmp_path_str}' AS enc KEY '{_APP_KEY}'")
        src.execute("SELECT sqlcipher_export('enc')")
        src.execute("DETACH DATABASE enc")
        src.close()

        # Verify the encrypted file is readable
        verify = cipher_sqlite3.connect(str(tmp_path), timeout=5.0)
        verify.execute("PRAGMA cipher_memory_security=OFF")
        # f-string interpolation is safe only while _APP_KEY remains a
        # controlled constant guarded by the module-level assertion above.
        verify.execute(f"PRAGMA key='{_APP_KEY}'")
        verify.execute("SELECT count(*) FROM sqlite_master")
        verify.close()

        # Swap files
        shutil.copy2(str(db_path), str(backup_path))
        os.replace(str(tmp_path), str(db_path))
        logger.info("DB encryption complete. Backup: %s", backup_path.name)
    except Exception:
        logger.exception("DB encryption failed")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
