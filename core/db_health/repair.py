"""DB repair operations (compatibility facade)."""

from .repair_auto import auto_repair_db
from .repair_dump import dump_and_restore

__all__ = [
    "auto_repair_db",
    "dump_and_restore",
]
