"""Thread-local SQLite connection pooling helpers.

Connection caching is per-thread, but the **act of opening** a SQLCipher
connection in WAL mode is serialized process-wide via a per-DB-path lock
(``_get_open_lock``). Two threads racing on the first ``sqlite3.connect()``
to a WAL-mode SQLCipher DB has been observed to corrupt the wal-index
(``tags.db-shm``): one thread's open path enters the "first connection
recovery" branch and unlinks/recreates the SHM file while another thread
has already mmap'd the old inode. The result is two connections viewing
disjoint SHM inodes, coordination breaks, and subsequent reads surface as
``database disk image is malformed`` / ``disk I/O error`` across every
extension that touches the same DB. ``mmap_size=0`` only disables the main
DB-file mmap; SHM is **always** mmap'd in WAL mode and cannot be opted out.

The serialized open window is hit only on cache miss (≈ once per thread
per DB), so the lock contention is bounded to startup. Steady-state reads
hit the thread-local cache and skip the lock entirely.
"""

import contextlib
import logging
import os
import threading
import time

from core.services_core.app_runtime_state import get_db_path, get_vectors_db_path
from core.services_core.db_cipher import apply_key, sqlite3
from core.services_core.db_state_functions import register_custom_functions
from core.services_core.db_state_runtime import ensure_db_migrated, ensure_vectors_db_ready

logger = logging.getLogger(__name__)

_local = threading.local()

# Per-DB-path locks that serialize the *open* path (sqlite3.connect + apply_key
# + PRAGMA setup + SHM warm-up read) across threads in the same process. See
# the module docstring for the SHM-race rationale. Lookup is itself guarded by
# ``_open_locks_guard`` so creating the first lock for a path is also safe.
_open_locks: dict[str, threading.Lock] = {}
_open_locks_guard = threading.Lock()
_readonly_generation = 0
_readonly_generation_lock = threading.Lock()

# Spread reconnects over this many seconds to avoid 16 db-pool threads all
# hitting _get_open_lock for PBKDF2 re-derivation simultaneously.
# Each thread schedules its own reconnect at a deterministic offset based on
# thread-name hash, so the lock contention window is effectively serialized.
_READONLY_RECONNECT_STAGGER = 3.5


def invalidate_readonly_connections() -> None:
    """Make cached readonly connections reopen on their next access."""
    global _readonly_generation
    with _readonly_generation_lock:
        _readonly_generation += 1


def _get_open_lock(path: str) -> threading.Lock:
    with _open_locks_guard:
        lock = _open_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _open_locks[path] = lock
        return lock


def _stat_inode(path: str) -> int | None:
    try:
        return os.stat(path).st_ino
    except OSError:
        return None


def _is_connection_alive(con: sqlite3.Connection) -> bool:
    """Probe the connection with a query that exercises the DB file (and WAL).

    ``SELECT 1`` is a constant and does not touch the database file, so it
    cannot detect a stale fd on tags.db / tags.db-wal / tags.db-shm. Reading
    from ``sqlite_schema`` forces SQLite to consult the page cache and WAL
    machinery, so a deleted-but-still-open WAL inode (the typical pattern when
    an operator replaces the DB file externally) surfaces as an exception
    here instead of breaking a later application query with ``disk I/O error``.
    """
    try:
        con.execute("SELECT name FROM sqlite_schema LIMIT 1").fetchone()
        return True
    except Exception:
        return False


def _get_cached_connection(
    attr: str, path_attr: str, inode_attr: str, current_path: str,
) -> sqlite3.Connection | None:
    con = getattr(_local, attr, None)
    if con is None:
        return None
    cached_path = getattr(_local, path_attr, None)
    cached_inode = getattr(_local, inode_attr, None)
    current_inode = _stat_inode(current_path)
    if (
        cached_path == current_path
        and current_inode is not None
        and cached_inode == current_inode
        and _is_connection_alive(con)
    ):
        return con
    if cached_inode is not None and current_inode != cached_inode:
        # Operator replaced the DB file externally (e.g. corruption recovery
        # by mv into place). Cached fds now point at the unlinked inode.
        logger.warning(
            "DB inode changed for %s (cached=%s current=%s) — dropping cached connection",
            current_path, cached_inode, current_inode,
        )
    with contextlib.suppress(Exception):
        con.close()
    setattr(_local, attr, None)
    setattr(_local, path_attr, None)
    setattr(_local, inode_attr, None)
    return None


def _store_connection(
    attr: str, path_attr: str, inode_attr: str, path: str, con: sqlite3.Connection,
) -> None:
    setattr(_local, attr, con)
    setattr(_local, path_attr, path)
    setattr(_local, inode_attr, _stat_inode(path))


def _warm_up_shm(con: sqlite3.Connection) -> None:
    """Force WAL-index (SHM) attach/creation while still inside the open lock.

    Reading from ``sqlite_schema`` is the cheapest operation that forces SQLite
    to coordinate via the SHM in WAL mode. Doing this inside the per-path open
    lock guarantees that by the time a second thread acquires the lock, the
    SHM has already been created/attached by the first thread and the second
    thread's ``sqlite3.connect()`` just maps the existing inode.
    """
    with contextlib.suppress(Exception):
        con.execute("SELECT name FROM sqlite_schema LIMIT 1").fetchone()


def _apply_common_write_pragmas(con: sqlite3.Connection, *, row_factory: bool) -> sqlite3.Connection:
    apply_key(con)
    if row_factory:
        con.row_factory = sqlite3.Row
        register_custom_functions(con)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA cache_size=-64000")
    con.execute("PRAGMA temp_store=MEMORY")
    # mmap MUST be disabled for SQLCipher: mmap reads raw encrypted pages while
    # writes go through the page cache (decrypt → modify → re-encrypt), and the
    # two views can tear at page boundaries — observed as "database disk image
    # is malformed" followed by MemoryError on subsequent open. NOTE: this
    # disables the *main DB* mmap only; the SHM/wal-index is always mmap'd in
    # WAL mode and the open path must be serialized via _open_locks to avoid
    # SHM-recovery races. See module docstring.
    con.execute("PRAGMA mmap_size=0")
    return con


def get_db() -> sqlite3.Connection:
    ensure_db_migrated()
    db_path = str(get_db_path().resolve())
    con = _get_cached_connection("con_row", "con_row_path", "con_row_inode", db_path)
    if con is not None:
        return con
    with _get_open_lock(db_path):
        con = _apply_common_write_pragmas(
            sqlite3.connect(str(get_db_path()), timeout=10.0), row_factory=True,
        )
        _warm_up_shm(con)
    _store_connection("con_row", "con_row_path", "con_row_inode", db_path, con)
    return con


def get_raw_db() -> sqlite3.Connection:
    ensure_db_migrated()
    db_path = str(get_db_path().resolve())
    con = _get_cached_connection("con_raw", "con_raw_path", "con_raw_inode", db_path)
    if con is not None:
        return con
    with _get_open_lock(db_path):
        con = _apply_common_write_pragmas(
            sqlite3.connect(str(get_db_path()), timeout=10.0), row_factory=False,
        )
        _warm_up_shm(con)
    _store_connection("con_raw", "con_raw_path", "con_raw_inode", db_path, con)
    return con


def get_readonly_db() -> sqlite3.Connection:
    ensure_db_migrated()
    db_path = str(get_db_path().resolve())
    cached_generation = getattr(_local, "con_readonly_generation", None)
    existing = getattr(_local, "con_readonly", None)
    if cached_generation != _readonly_generation:
        if existing is not None:
            # Stagger reconnects across db-pool threads to avoid all 16 threads
            # hitting _get_open_lock for PBKDF2 re-derivation at the same instant
            # (observed as ~2.88 s latency spike: 16 × ~180 ms serialized under lock).
            # WAL-mode connections can safely read committed data until the stagger
            # deadline arrives, so in-flight queries are not affected.
            reconnect_after = getattr(_local, "con_readonly_reconnect_after", None)
            if reconnect_after is None:
                thread_hash = hash(threading.current_thread().name) & 0xFFFF
                jitter = (thread_hash / 0xFFFF) * _READONLY_RECONNECT_STAGGER
                _local.con_readonly_reconnect_after = time.monotonic() + jitter
                reconnect_after = _local.con_readonly_reconnect_after
            if time.monotonic() >= reconnect_after:
                _local.con_readonly_reconnect_after = None
                # Do NOT close `existing` here: an outer stack frame may still
                # hold this exact connection object (e.g. build_search_response
                # captured `con` and a nested get_readonly_db() via kv_state.get()
                # triggered this reconnect). Closing it would surface as
                # "Cannot operate on a closed database." on the held reference.
                # Drop the thread-local refs so the next access opens a fresh
                # connection; the old one is closed by its finalizer when the
                # last reference is released.
                _local.con_readonly = None
                _local.con_readonly_path = None
                _local.con_readonly_inode = None
                _local.con_readonly_generation = _readonly_generation
            # else: deadline not yet reached — return existing connection below;
            # generation intentionally not updated so the next call rechecks.
        else:
            # No existing connection: update generation without burst risk.
            _local.con_readonly_generation = _readonly_generation
    con = _get_cached_connection("con_readonly", "con_readonly_path", "con_readonly_inode", db_path)
    if con is not None:
        return con
    with _get_open_lock(db_path):
        con = sqlite3.connect(str(get_db_path()), timeout=5.0)
        apply_key(con)
        con.row_factory = sqlite3.Row
        register_custom_functions(con)
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA cache_size=-64000")
        con.execute("PRAGMA temp_store=MEMORY")
        # See _apply_common_write_pragmas: mmap is unsafe with SQLCipher.
        con.execute("PRAGMA mmap_size=0")
        _warm_up_shm(con)
    _store_connection("con_readonly", "con_readonly_path", "con_readonly_inode", db_path, con)
    _local.con_readonly_generation = _readonly_generation
    return con


def get_vectors_db() -> sqlite3.Connection:
    ensure_vectors_db_ready()
    vectors_path = str(get_vectors_db_path().resolve())
    con = _get_cached_connection("con_vectors", "con_vectors_path", "con_vectors_inode", vectors_path)
    if con is not None:
        return con
    with _get_open_lock(vectors_path):
        con = sqlite3.connect(str(get_vectors_db_path()), timeout=10.0)
        apply_key(con)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA cache_size=-32000")
        # See _apply_common_write_pragmas: mmap is unsafe with SQLCipher.
        con.execute("PRAGMA mmap_size=0")
        _warm_up_shm(con)
    _store_connection("con_vectors", "con_vectors_path", "con_vectors_inode", vectors_path, con)
    return con


def get_vectors_readonly_db() -> sqlite3.Connection:
    ensure_vectors_db_ready()
    vectors_path = str(get_vectors_db_path().resolve())
    con = _get_cached_connection("con_vectors_ro", "con_vectors_ro_path", "con_vectors_ro_inode", vectors_path)
    if con is not None:
        return con
    with _get_open_lock(vectors_path):
        con = sqlite3.connect(str(get_vectors_db_path()), timeout=5.0)
        apply_key(con)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA cache_size=-32000")
        # See _apply_common_write_pragmas: mmap is unsafe with SQLCipher.
        con.execute("PRAGMA mmap_size=0")
        con.execute("PRAGMA temp_store=MEMORY")
        _warm_up_shm(con)
    _store_connection("con_vectors_ro", "con_vectors_ro_path", "con_vectors_ro_inode", vectors_path, con)
    return con


def close_thread_connections() -> None:
    for attr in ("con_row", "con_raw", "con_readonly", "con_vectors", "con_vectors_ro"):
        con = getattr(_local, attr, None)
        if con is not None:
            with contextlib.suppress(Exception):
                con.close()
            setattr(_local, attr, None)
    for path_attr in (
        "con_row_path", "con_raw_path", "con_readonly_path",
        "con_vectors_path", "con_vectors_ro_path",
    ):
        setattr(_local, path_attr, None)
    for inode_attr in (
        "con_row_inode", "con_raw_inode", "con_readonly_inode",
        "con_vectors_inode", "con_vectors_ro_inode",
    ):
        setattr(_local, inode_attr, None)
    _local.con_readonly_generation = None
    _local.con_readonly_reconnect_after = None


def warm_up_main_db() -> None:
    """Open the main DB on the calling thread to establish the SHM cleanly.

    Intended to be called once by the main thread at server startup *before*
    spawning background threads. With the SHM in a stable state, subsequent
    concurrent opens from other threads attach to the existing inode instead
    of racing the first-connection recovery path.

    Idempotent: calls ``get_db()`` which is itself cached per-thread.
    """
    con = get_db()
    with contextlib.suppress(Exception):
        con.execute("SELECT 1").fetchone()


def get_db_parser_version(con: sqlite3.Connection) -> int:
    try:
        row = con.execute(
            "SELECT MIN(COALESCE(parser_version, 1)) FROM files WHERE is_deleted=0"
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 1
    except sqlite3.OperationalError:
        return 1
