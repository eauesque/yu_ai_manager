"""DB schema initialization for legacy tagdb CLI."""

import sqlite3

from .tagdb_db_schema_common import table_has_column
from .tagdb_db_schema_sql import BASE_SCHEMA_SQL, FTS_SCHEMA_SQL


def init_db(con: sqlite3.Connection, enable_fts: bool) -> None:
    con.executescript(BASE_SCHEMA_SQL)

    if not table_has_column(con, "files", "not_modified"):
        con.execute("ALTER TABLE files ADD COLUMN not_modified INTEGER NOT NULL DEFAULT 0")

    if enable_fts:
        con.executescript(FTS_SCHEMA_SQL)

    con.commit()
