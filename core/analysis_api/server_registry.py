"""AI server registry compatibility facade.

Actual implementation is split into:
- server_model.py  -- data model, read ops, resolution, helpers
- server_crud.py   -- CRUD operations, testing, legacy migration

Internal modules should import those concrete modules directly. This file
exists to preserve older import paths.
"""

# Re-export everything so existing imports keep working unchanged.

from .server_crud import (  # noqa: F401
    add_server,
    get_servers_with_status,
    migrate_from_legacy,
    remove_server,
    reorder_servers,
    set_active_server,
    test_server,
    update_server,
)
from .server_discovery import (  # noqa: F401
    get_discovered_candidates,
    ignore_discovered_candidate,
    match_discovered_candidate,
    register_discovered_candidate,
    run_discovered_candidate_test,
    unignore_discovered_candidate,
    unmatch_discovered_candidate,
)
from .server_model import (  # noqa: F401
    VALID_TYPES,
    ServerEntry,
    _build_kwargs,
    _check_available,
    _is_hailo_vlm_available,
    _is_ollama_available,
    _is_openai_compat_available,
    _is_server_local,
    _legacy_to_entry,
    _slugify,
    _validate_and_build,
    get_active_server_id,
    get_all_servers,
    get_language,
    has_servers,
    is_fallback_local_only,
    resolve_active_server,
)
