"""DB connection helpers."""

from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3
from core.services_core.db_state import register_custom_functions


def connect_db(db_path: Path) -> sqlite3.Connection:
    from core.services_core.db_state import _ensure_db_migrated
    _ensure_db_migrated()
    con = sqlite3.connect(str(db_path), timeout=10.0)
    apply_key(con)
    register_custom_functions(con)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=10000;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute("PRAGMA cache_size=-64000;")
    con.execute("PRAGMA temp_store=MEMORY;")
    # mmap is unsafe with SQLCipher (see db_state_connections._apply_common_write_pragmas).
    con.execute("PRAGMA mmap_size=0;")
    return con


def table_has_column(con: sqlite3.Connection, table: str, col: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(len(r) >= 2 and r[1] == col for r in rows)
