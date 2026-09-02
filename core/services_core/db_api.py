"""Database/global-state API for app entrypoints."""

from core.services_core.db_scan_progress import WebUIProgressCallback, scan_lock, scan_state
from core.services_core.db_state import (
    get_config,
    get_db,
    get_db_parser_version,
    get_db_path,
    get_raw_db,
    get_readonly_db,
    get_start_time,
    get_startup_migration_info,
    get_startup_status,
    get_vectors_db,
    get_vectors_readonly_db,
    init_app_state,
    is_boot_ready,
    set_boot_ready,
    set_startup_migration_info,
    set_startup_status,
)

__all__ = [
    "WebUIProgressCallback",
    "get_config",
    "get_db",
    "get_db_parser_version",
    "get_db_path",
    "get_raw_db",
    "get_readonly_db",
    "get_start_time",
    "get_startup_migration_info",
    "get_startup_status",
    "get_vectors_db",
    "get_vectors_readonly_db",
    "init_app_state",
    "is_boot_ready",
    "set_boot_ready",
    "set_startup_migration_info",
    "set_startup_status",
    "scan_lock",
    "scan_state",
]
