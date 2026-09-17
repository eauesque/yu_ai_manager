"""Database/file lookup helpers for Freeze & Pull-back routes."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def resolve_image_path(file_id: int) -> str:
    """Resolve image path from file_id."""
    try:
        from core.services_core.db_api import get_readonly_db

        con = get_readonly_db()
        row = con.execute(
            "SELECT path FROM files WHERE id = ? AND is_deleted = 0",
            (file_id,),
        ).fetchone()
        if row and os.path.isfile(row[0]):
            return row[0]
    except Exception as exc:
        logger.warning("Failed to resolve file_id %d: %s", file_id, exc)
    return ""
