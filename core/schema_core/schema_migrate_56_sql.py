"""SQL payload assembly for migration 56."""

from .schema_migrate_56_sql_tables_a import TABLES_SQL_A
from .schema_migrate_56_sql_tables_b import TABLES_SQL_B

TABLES_SQL = TABLES_SQL_A + "\n" + TABLES_SQL_B
COLUMNS_SQL = [
    ("files", "phash", "TEXT"),
    ("templates", "prompt_lang", "TEXT DEFAULT ''"),
    ("templates", "prompt_lang_confidence", "REAL DEFAULT 0.0"),
]
