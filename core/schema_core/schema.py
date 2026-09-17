"""DB schema facade (connection/init/migration)."""

from .schema_connect import connect_db
from .schema_constants import CURRENT_PARSER_VERSION, CURRENT_SCHEMA_VERSION
from .schema_init import init_db
from .schema_migrate import migrate_db
from .schema_migrate_version import get_schema_version, set_schema_version

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "CURRENT_PARSER_VERSION",
    "connect_db",
    "init_db",
    "get_schema_version",
    "set_schema_version",
    "migrate_db",
]
