"""DB accessor helpers for Hailo chat session persistence."""

from __future__ import annotations


def get_hailo_chat_write_db():
    from core.services_core.db_state import get_db

    return get_db()


def get_hailo_chat_read_db():
    from core.services_core.db_state import get_readonly_db

    return get_readonly_db()
