"""Synchronous helpers for LAN share routes."""

from __future__ import annotations


def get_collection_zip_filename(collection_id: int) -> str:
    """Return a stable ZIP download filename for a collection."""
    from core.services_core.db_api import get_db

    con = get_db()
    row = con.execute("SELECT name FROM collections WHERE id=?", (collection_id,)).fetchone()
    coll_name = row[0] if row else "collection"
    return f"{coll_name}.zip"
