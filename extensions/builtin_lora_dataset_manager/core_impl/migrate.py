"""DB migration for LoRA Dataset Manager."""

import sqlite3

from core.extensions_core.lifecycle.extensions_db_migrate import (
    get_extension_schema_version,
    set_extension_schema_version,
)

_EXT_NAME = "builtin-lora-dataset-manager"


def on_db_migrate(con: sqlite3.Connection) -> None:
    """Create extension tables idempotently."""
    cur = get_extension_schema_version(con, _EXT_NAME)

    if cur < 1:
        con.execute("""
            CREATE TABLE IF NOT EXISTS lora_projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                concept     TEXT NOT NULL,
                repeat      INTEGER DEFAULT 10,
                base_model  TEXT DEFAULT 'sdxl',
                tag_exclude TEXT DEFAULT '[]',
                tag_preset  TEXT DEFAULT '',
                search_query TEXT DEFAULT '',
                file_ids    TEXT DEFAULT '[]',
                created_at  INTEGER,
                updated_at  INTEGER
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS lora_tag_presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                tags        TEXT NOT NULL DEFAULT '[]',
                created_at  INTEGER,
                updated_at  INTEGER
            )
        """)
        set_extension_schema_version(con, _EXT_NAME, 1, "lora_projects + lora_tag_presets")

    if cur < 2:
        columns = {
            row[1] for row in con.execute("PRAGMA table_info(lora_projects)").fetchall()
        }
        if "model_scope" not in columns:
            con.execute(
                "ALTER TABLE lora_projects "
                "ADD COLUMN model_scope TEXT NOT NULL DEFAULT 'all'"
            )
        set_extension_schema_version(con, _EXT_NAME, 2, "lora project model_scope")

    con.commit()
