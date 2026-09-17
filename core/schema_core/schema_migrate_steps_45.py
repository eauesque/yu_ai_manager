"""Schema migration 45: Add language detection columns.

Add prompt_lang / prompt_lang_confidence to the templates table.
Add language / language_confidence to the chat_conversations table.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

import contextlib

from .schema_migrate_version import set_schema_version


def apply_migration_45(con: sqlite3.Connection) -> None:
    """Add language detection columns to templates and chat_conversations."""
    logger.info("  -> Migration 45: language detection columns")

    # Add prompt language columns to templates table
    for col, col_type, default in [
        ("prompt_lang", "TEXT", "''"),
        ("prompt_lang_confidence", "REAL", "0.0"),
    ]:
        with contextlib.suppress(Exception):  # column may already exist
            con.execute(
                f"ALTER TABLE templates ADD COLUMN {col} {col_type} DEFAULT {default}"
            )

    # Add language columns to chat_conversations table
    try:
        con.execute("""
            SELECT id FROM chat_conversations LIMIT 0
        """)
        # Only add columns if table exists
        for col, col_type, default in [
            ("language", "TEXT", "''"),
            ("language_confidence", "REAL", "0.0"),
        ]:
            with contextlib.suppress(Exception):
                con.execute(
                    f"ALTER TABLE chat_conversations ADD COLUMN {col} {col_type} DEFAULT {default}"
                )
    except Exception:
        # Skip if chat_conversations table doesn't exist
        logger.debug("  chat_conversations テーブルが存在しない - スキップ")

    set_schema_version(con, 45, "language detection columns")
