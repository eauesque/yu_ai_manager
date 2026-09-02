"""Chatlog store: SQL CRUD + FTS5.

ensure_tables() creates tables idempotently.
All functions take ``con: sqlite3.Connection`` as the first argument.

CRUD operations are split into store_crud.py. This module re-exports
them for backward compatibility.
"""

from __future__ import annotations

import sqlite3
import threading

from core.services_core.chatlog_store_service import ensure_chatlog_tables
from core.services_core.db_write import submit_db_write

# CRUD functions split to store_crud.py -- re-export for backward compat
from .store_crud import (  # noqa: F401
    delete_conversation,
    find_by_external_id,
    get_conversation,
    get_stats,
    insert_conversation,
    insert_messages,
    list_conversations,
)

# Search functions split to store_search.py -- re-export for backward compat
from .store_search import (  # noqa: F401
    count_conversations,
    search_messages,
)

_init_lock = threading.Lock()
_initialized = False


# -- Table initialization -----------------------------------------------

def ensure_tables(con: sqlite3.Connection | None = None) -> None:
    """Create chat_conversations + chat_messages + FTS5 tables idempotently."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        def _init() -> None:
            ensure_chatlog_tables(con)

        if con is not None:
            _init()
        else:
            submit_db_write(_init)
        _initialized = True
