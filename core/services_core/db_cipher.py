"""SQLCipher import shim and application key management."""

import logging

from sqlcipher3 import dbapi2 as sqlite3  # noqa: F401 — re-exported as sqlite3

_APP_KEY = "yu-ai-manager-v1-cipher-2026"
assert not any(ch in _APP_KEY for ch in ("'", ";", "\\")), (
    "_APP_KEY must remain a controlled SQLCipher key literal"
)
# Characters a caller-supplied key may not contain.
#
# The first three close the SQLCipher literal itself: `PRAGMA key` is built by
# f-string interpolation, so a quote, a semicolon or a backslash would turn the
# key into a second statement.
#
# The rest are not injection -- they are what the log scrubber cannot cover.
# Scrubbing is key-name based (`db_key=<value>`) and its value class stops at
# the first of `\s , ; & " ' } ]` (crates/yu-server/src/logs/scrub.rs, and the
# Python side mirrors it), so a key containing one of those would be printed
# in part wherever a log line carries it. Refusing them keeps "the key never
# reaches a log" true rather than nearly true.
_KEY_FORBIDDEN = ("'", '"', ";", "\\", "&", ",", "}", "]")


def validate_db_key(key: str) -> str:
    """Return ``key`` if it is safe to interpolate and to log around."""
    if not key:
        raise ValueError("database key must not be empty")
    if any(ch.isspace() for ch in key):
        raise ValueError("database key must not contain whitespace")
    bad = sorted({ch for ch in key if ch in _KEY_FORBIDDEN})
    if bad:
        raise ValueError(
            "database key must not contain any of "
            + " ".join(repr(ch) for ch in _KEY_FORBIDDEN)
            + f" (found {' '.join(repr(ch) for ch in bad)})"
        )
    return key


# True whenever this module imported successfully, i.e. whenever every
# connection that goes through ``apply_key`` is encrypted. Callers that inspect
# database files on disk need this: an encrypted file does NOT begin with the
# plaintext ``SQLite format 3\0`` magic, so a validator that checks for it
# rejects every backup this build produces. Importers that fall back to the
# stdlib ``sqlite3`` on ImportError must treat the flag as False.
ENCRYPTION_ENABLED = True
logger = logging.getLogger(__name__)
_log_level_initialized = False


def _ensure_cipher_log_level_quiet() -> None:
    """Lower SQLCipher's log threshold from WARN to ERROR (process-global).

    SQLCipher 4.12 still emits ``WARN MEMORY sqlcipher_mlock: VirtualLock()
    returned 0 LastError=1453`` even with ``cipher_memory_security=OFF``,
    because some VirtualLock paths bypass that flag and fire whenever
    Windows' working set quota is full. The cumulative noise from many
    thread-local cached connections (16 db-pool + heavy-io + writer +
    blocking pools, plus per-DB-file connections) drowns the real log.
    ``cipher_log_level`` is connection-syntax but process-global state, so
    setting it once via a throwaway connection silences subsequent ones.
    """
    global _log_level_initialized
    if _log_level_initialized:
        return
    try:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("PRAGMA cipher_log_level=ERROR")
        finally:
            probe.close()
    except Exception as exc:
        # If the pragma is unsupported in some future SQLCipher build,
        # fail open — the warnings are noise, not correctness.
        logger.debug("cipher_log_level not supported: %s", exc)
        pass
    _log_level_initialized = True


def apply_key(con, key: str | None = None) -> None:
    """Apply an encryption key to a freshly opened connection.

    ``key`` defaults to the application key, which is what every in-process
    caller wants and what the desktop build's server is started with. Pass one
    explicitly only for a database encrypted with an operator-chosen key -- a
    systemd deployment generates its own ``YU_DB_KEY``, and this process
    cannot open such a database with the application key at all.

    Also lowers SQLCipher's log threshold to ERROR on first call to
    suppress mlock warnings under working-set pressure (see
    ``_ensure_cipher_log_level_quiet``) and enforces ``mmap_size=0`` to
    block the mmap+SQLCipher torn-write corruption pattern documented in
    ``docs/development/development_docs/SQLCIPHER_MMAP_CORRUPTION.md``.
    """
    _ensure_cipher_log_level_quiet()
    # cipher_memory_security defaults to 0 in this build, but issue OFF
    # explicitly anyway — cheap, idempotent, and survives any upstream
    # default flip.
    con.execute("PRAGMA cipher_memory_security=OFF")
    # f-string interpolation is safe only while the key is a controlled
    # literal: _APP_KEY is guarded by the module-level assertion above, and a
    # caller-supplied one by validate_db_key.
    effective = _APP_KEY if key is None else validate_db_key(key)
    con.execute(f"PRAGMA key='{effective}'")

    # mmap MUST be disabled on every SQLCipher connection. mmap reads raw
    # encrypted pages while writes go through the page cache (decrypt →
    # modify → re-encrypt) and the two can tear at page boundaries —
    # observed as "database disk image is malformed" followed by MemoryError
    # on subsequent open. This single line guards every ad-hoc connect()
    # site that uses apply_key(), in addition to the explicit PRAGMA in
    # the connection-pool helpers.
    con.execute("PRAGMA mmap_size=0")


__all__ = ["sqlite3", "apply_key", "validate_db_key", "_APP_KEY", "ENCRYPTION_ENABLED"]
