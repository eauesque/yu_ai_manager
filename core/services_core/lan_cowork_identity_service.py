"""Persistent LAN Cowork identity backed by a single Ed25519 seed."""

from __future__ import annotations

import sqlite3

from core.crypto_identity import (
    derive_peer_id,
    ed25519_pubkey_bytes,
    generate_ed25519_seed,
    x25519_pubkey_bytes,
)

_PAIRING_COLUMNS = (
    ("pubkey", "BLOB"),
    ("x25519_pk", "BLOB"),
    ("commit_hash", "BLOB"),
    ("sas", "TEXT"),
    ("source_ip", "TEXT"),
)


def _existing_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def apply_crypto_identity_migration(con: sqlite3.Connection) -> None:
    """Clean-cut migration to seed-based crypto identity."""
    existing = _existing_columns(con, "peer_pairing_requests")
    for name, coltype in _PAIRING_COLUMNS:
        if name not in existing:
            con.execute(f"ALTER TABLE peer_pairing_requests ADD COLUMN {name} {coltype}")
    con.execute("DELETE FROM peer_pairing_requests")
    con.execute("DELETE FROM peer_tokens")
    con.execute("DELETE FROM lan_cowork_identity WHERE key='peer_id'")
    con.execute("DELETE FROM lan_cowork_identity WHERE key='ed25519_pubkey'")
    con.execute("DELETE FROM lan_cowork_identity WHERE key='x25519_pubkey'")
    con.commit()


def load_or_create_identity_from_con(
    con: sqlite3.Connection,
) -> tuple[str, bytes, bytes, bytes]:
    """Return (peer_id, ed25519_seed, ed25519_pubkey, x25519_pubkey)."""
    row = con.execute(
        "SELECT value FROM lan_cowork_identity WHERE key='ed25519_seed'"
    ).fetchone()
    if row is not None:
        seed = bytes(row[0])
    else:
        seed = generate_ed25519_seed()
        con.execute(
            "INSERT OR IGNORE INTO lan_cowork_identity (key, value) "
            "VALUES ('ed25519_seed', ?)",
            (seed,),
        )
        con.commit()
        row = con.execute(
            "SELECT value FROM lan_cowork_identity WHERE key='ed25519_seed'"
        ).fetchone()
        seed = bytes(row[0])

    pubkey = ed25519_pubkey_bytes(seed)
    x25519_pk = x25519_pubkey_bytes(seed)
    peer_id = derive_peer_id(pubkey)
    return peer_id, seed, pubkey, x25519_pk


def load_or_create_identity() -> tuple[str, bytes, bytes, bytes]:
    """Production entry point using the project DB connection."""
    from core.services_core.db_state import get_db

    return load_or_create_identity_from_con(get_db())
