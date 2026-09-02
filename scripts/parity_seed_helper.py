"""Shared DB seed helper for Phase 1 and Phase 3 parity checks."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE_A1111 = (
    REPO
    / "crates"
    / "meta-extract"
    / "tests"
    / "fixtures"
    / "inspect_parity"
    / "a1111.png"
)
PARITY_COLLECTION_NAME = "parity-test-collection"


def seed_parity_db(db_path: Path) -> dict[str, int]:
    """Create a fresh SQLite DB seeded with a file and a parity collection."""
    import sys

    sys.path.insert(0, str(REPO))
    from core.scan_core.scanner import scan_one
    from core.schema_core.schema_init import init_db

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        for _ in range(5):
            try:
                db_path.unlink()
                break
            except PermissionError:
                time.sleep(0.5)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    init_db(con, enable_fts=False)

    scan_one(con, FIXTURE_A1111, {}, force=True, compute_hash=False)
    file_id: int = con.execute("SELECT id FROM files LIMIT 1").fetchone()["id"]

    if not con.execute("SELECT 1 FROM collections WHERE id=1").fetchone():
        con.execute(
            "INSERT INTO collections (id, name, sort_order, created_at) VALUES (1, 'Favorites', 0, ?)",
            (int(time.time()),),
        )

    con.execute(
        "INSERT INTO collections (name, sort_order, created_at) VALUES (?, 0, ?)",
        (PARITY_COLLECTION_NAME, int(time.time())),
    )
    collection_id: int = con.execute(
        "SELECT id FROM collections WHERE name = ? ORDER BY id DESC LIMIT 1",
        (PARITY_COLLECTION_NAME,),
    ).fetchone()["id"]

    # tag_dict/info parity test requires at least one entry
    con.execute(
        "INSERT OR IGNORE INTO tag_dictionary (tag_name, category, post_count) VALUES ('cat', 4, 500000)",
    )

    # chatlog search parity test requires FTS virtual table
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts USING fts5(content, tokenize='unicode61')"
    )

    con.commit()
    con.close()
    return {"file_id": file_id, "collection_id": collection_id}


def seed_ids_from_existing_db(db_path: Path) -> dict[str, int]:
    """Read an already-seeded DB and return known IDs for variable resolution."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    file_row = con.execute("SELECT id FROM files LIMIT 1").fetchone()
    coll_row = con.execute(
        "SELECT id FROM collections WHERE name = ? ORDER BY id DESC LIMIT 1",
        (PARITY_COLLECTION_NAME,),
    ).fetchone()
    con.close()
    return {
        "file_id": file_row["id"] if file_row else 0,
        "collection_id": coll_row["id"] if coll_row else 0,
    }
