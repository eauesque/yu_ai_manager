"""SQL scripts for schema initialization and optional features."""

from .schema_sql_base import BASE_SCHEMA_SQL_BASE
from .schema_sql_fts import FTS_SCHEMA_SQL
from .schema_sql_integrations import BASE_SCHEMA_SQL_INTEGRATIONS
from .schema_sql_media import BASE_SCHEMA_SQL_MEDIA

BASE_SCHEMA_SQL = "".join(
    [
        BASE_SCHEMA_SQL_BASE,
        "\n",
        BASE_SCHEMA_SQL_MEDIA,
        "\n",
        BASE_SCHEMA_SQL_INTEGRATIONS,
    ]
)

__all__ = ["BASE_SCHEMA_SQL", "FTS_SCHEMA_SQL"]
