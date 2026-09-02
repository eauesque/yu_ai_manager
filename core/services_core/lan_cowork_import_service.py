"""Default DB provider helpers for LAN Cowork import flows."""

from __future__ import annotations

import sqlite3


def get_import_write_db() -> sqlite3.Connection:
    from core.services_core.db_state import get_db

    return get_db()


def get_import_read_db() -> sqlite3.Connection:
    from core.services_core.db_state import get_readonly_db

    return get_readonly_db()
