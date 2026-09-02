"""AI server model compatibility facade.

Split into:
  - server_model_data: data model, read operations, legacy compat, validation
  - server_model_resolve: server resolution and availability checking

Internal modules should import those concrete modules directly. This file
exists to preserve the older combined import path.
"""

# Re-export all public symbols for backward compatibility
from core.analysis_api.server_model_data import (  # noqa: F401
    _MAX_SERVERS,
    VALID_TYPES,
    ServerEntry,
    _legacy_to_entry,
    _slugify,
    _validate_and_build,
    get_active_server_id,
    get_all_servers,
    get_language,
    has_servers,
    is_fallback_local_only,
)
from core.analysis_api.server_model_resolve import (  # noqa: F401
    _build_kwargs,
    _check_available,
    _is_hailo_vlm_available,
    _is_ollama_available,
    _is_openai_compat_available,
    _is_server_local,
    resolve_active_server,
)

__all__ = [
    "VALID_TYPES",
    "ServerEntry",
    "get_active_server_id",
    "get_all_servers",
    "get_language",
    "has_servers",
    "is_fallback_local_only",
    "resolve_active_server",
    "_MAX_SERVERS",
    "_build_kwargs",
    "_check_available",
    "_is_hailo_vlm_available",
    "_is_ollama_available",
    "_is_openai_compat_available",
    "_is_server_local",
    "_legacy_to_entry",
    "_slugify",
    "_validate_and_build",
]
