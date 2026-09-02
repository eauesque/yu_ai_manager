"""SQLCipher import shim and application key management."""

import logging

from sqlcipher3 import dbapi2 as sqlite3  # noqa: F401 — re-exported as sqlite3

_APP_KEY = "yu-ai-manager-v1-cipher-2026"
assert not any(ch in _APP_KEY for ch in ("'", ";", "\\")), (
    "_APP_KEY must remain a controlled SQLCipher key literal"
)
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


def apply_key(con) -> None:
    """Apply the application encryption key to a freshly opened connection.

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
    # f-string interpolation is safe only while _APP_KEY remains a controlled
    # constant guarded by the module-level literal assertion above.
    con.execute(f"PRAGMA key='{_APP_KEY}'")
    # mmap MUST be disabled on every SQLCipher connection. mmap reads raw
    # encrypted pages while writes go through the page cache (decrypt →
    # modify → re-encrypt) and the two can tear at page boundaries —
    # observed as "database disk image is malformed" followed by MemoryError
    # on subsequent open. This single line guards every ad-hoc connect()
    # site that uses apply_key(), in addition to the explicit PRAGMA in
    # the connection-pool helpers.
    con.execute("PRAGMA mmap_size=0")


__all__ = ["sqlite3", "apply_key", "_APP_KEY"]
