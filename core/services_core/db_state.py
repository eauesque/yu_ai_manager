"""DB connection helpers backed by application runtime state."""

_cipher_migration_done = False
_cipher_migration_path: str | None = None
_vectors_ready_done = False
_vectors_ready_path: str | None = None

from core.services_core.app_runtime_state import (  # noqa: F401
    get_config,
    get_db_path,
    get_start_time,
    get_startup_migration_info,
    get_startup_status,
    get_vectors_db_path,
    init_app_state,
    is_boot_ready,
    set_boot_ready,
    set_startup_migration_info,
    set_startup_status,
)
from core.services_core.db_state_connections import (
    close_thread_connections,
    get_db,
    get_db_parser_version,
    get_raw_db,
    get_readonly_db,
    get_vectors_db,
    get_vectors_readonly_db,
    invalidate_readonly_connections,
)
from core.services_core.db_state_functions import (
    nfkc_lower,
    register_custom_functions,
)
from core.services_core.db_state_runtime import (
    ensure_db_migrated,
    ensure_vectors_db_ready,
)

# Legacy private aliases kept for startup/import compatibility.
_ensure_db_migrated = ensure_db_migrated
_ensure_vectors_db_ready = ensure_vectors_db_ready

__all__ = [
    "close_thread_connections",
    "ensure_db_migrated",
    "ensure_vectors_db_ready",
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
    "get_vectors_db_path",
    "get_vectors_readonly_db",
    "invalidate_readonly_connections",
    "init_app_state",
    "is_boot_ready",
    "nfkc_lower",
    "register_custom_functions",
    "set_boot_ready",
    "set_startup_migration_info",
    "set_startup_status",
]
