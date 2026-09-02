"""Common DB connection/schema helpers for legacy tagdb CLI."""

import logging
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3

logger = logging.getLogger(__name__)


def connect_db(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    apply_key(con)
    con.row_factory = sqlite3.Row

    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=10000;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute("PRAGMA cache_size=-64000;")
    con.execute("PRAGMA temp_store=MEMORY;")
    # mmap is unsafe with SQLCipher (see db_state_connections._apply_common_write_pragmas).
    con.execute("PRAGMA mmap_size=0;")

    return con


def file_etag(path: Path) -> str:
    import hashlib

    st = path.stat()
    size = int(st.st_size)
    ext = path.suffix.lower()

    if ext in (".jpg", ".jpeg"):
        full_threshold = 2_000_000
        chunk_size = 256_000
        use_mid = False
    elif ext == ".png":
        full_threshold = 2_000_000
        chunk_size = 512_000
        use_mid = False
    elif ext == ".webm":
        full_threshold = 4_000_000
        chunk_size = 512_000
        use_mid = True
    else:
        full_threshold = 2_000_000
        chunk_size = 256_000
        use_mid = False

    h = hashlib.sha256()
    h.update(str(size).encode("ascii"))
    h.update(ext.encode("ascii", errors="ignore"))

    def _read_full(f) -> None:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)

    with path.open("rb") as f:
        if size <= full_threshold:
            _read_full(f)
        else:
            h.update(f.read(chunk_size))
            if use_mid and size > (chunk_size * 3):
                try:
                    mid = max(0, (size // 2) - (chunk_size // 2))
                    f.seek(mid)
                    h.update(f.read(chunk_size))
                except Exception as exc:
                    logger.debug("Mid-seek hash read failed: %s", exc)
            try:
                if size > chunk_size:
                    f.seek(max(0, size - chunk_size))
                    h.update(f.read(chunk_size))
            except Exception:
                f.seek(0)
                _read_full(f)

    return h.hexdigest()


def table_has_column(con: sqlite3.Connection, table: str, col: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(len(r) >= 2 and r[1] == col for r in rows)
