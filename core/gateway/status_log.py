from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.services_core.db_cipher import apply_key, sqlite3

# tags.db is SQLCipher-encrypted. Use the cipher shim and apply_key on every
# connection. Using stdlib sqlite3 here caused silent write failures and was
# observed to corrupt the SQLCipher WAL via concurrent stdlib-vs-SQLCipher
# frame contention — see docs/development/development_docs/SQLCIPHER_MMAP_CORRUPTION.md.


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=10.0)
    apply_key(con)
    con.execute("PRAGMA busy_timeout=10000")
    _ensure_table(con)
    return con


def _ensure_table(con: sqlite3.Connection) -> None:
    """Create gateway_status_transitions if missing (e.g. schema init partial failure)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS gateway_status_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backend_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            last_request_id TEXT,
            metadata TEXT
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_status_backend_time
            ON gateway_status_transitions(backend_id, timestamp DESC)
    """)
    con.commit()


def record_transition(
    db_path: Path,
    backend_id: str,
    from_state: str,
    to_state: str,
    timestamp: datetime,
    last_request_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    ts = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    con = _connect(db_path)
    try:
        con.execute(
            "INSERT INTO gateway_status_transitions "
            "(backend_id, timestamp, from_state, to_state, last_request_id, metadata) "
            "VALUES (?,?,?,?,?,?)",
            (
                backend_id,
                ts,
                from_state,
                to_state,
                last_request_id,
                json.dumps(metadata) if metadata else None,
            ),
        )
        con.commit()
    finally:
        con.close()


def get_latest_states(db_path: Path) -> dict[str, dict]:
    con = _connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        states = {
            r["backend_id"]: {
                "state": r["to_state"],
                "last_transition": r["timestamp"],
            }
            for r in con.execute("""
                SELECT backend_id, to_state, timestamp FROM gateway_status_transitions
                WHERE id IN (
                    SELECT MAX(id) FROM gateway_status_transitions GROUP BY backend_id
                )
            """)
        }
    finally:
        con.close()
    return states


def gc_old_transitions(db_path: Path, retain_days: int = 90) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=retain_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    con = _connect(db_path)
    try:
        cur = con.execute(
            "DELETE FROM gateway_status_transitions WHERE timestamp < ?", (cutoff,)
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()
