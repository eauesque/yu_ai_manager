"""Schema initialization wrapper for MD Viewer store."""

from __future__ import annotations

import sqlite3

from core.services_core.md_viewer_store_service import ensure_md_viewer_tables


def ensure_tables(con: sqlite3.Connection | None = None) -> None:
    """Create md_files + md_files_fts tables (idempotent)."""
    ensure_md_viewer_tables(con)
