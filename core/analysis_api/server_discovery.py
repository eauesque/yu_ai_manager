"""AI server discovery compatibility facade.

Keep this import path stable for external callers and tests that patch
discovery helpers by name. Internal modules should prefer concrete
``server_discovery_*`` helpers and direct dependencies instead of importing
through this facade.
"""

from __future__ import annotations

from core.analysis_api.config_ops import _is_private_url
from core.configuration.api import load_config_json, save_config_json
from core.llm_endpoint_discovery.local_detect import (
    discover_local_ollama_endpoints,
)
from core.llm_endpoint_discovery.probes import probe_openai_compat_models
from core.settings_core.secret_store import decrypt

from .server_discovery_candidates import (
    _discover_known_openai_compat_candidates,
    _discover_local_hailo_candidates,
    get_discovered_candidates,
)
from .server_discovery_match import (
    _cleanup_discovery_metadata,
    _load_discovery_ignored,
    _load_discovery_matches,
    ignore_discovered_candidate,
    match_discovered_candidate,
    unignore_discovered_candidate,
    unmatch_discovered_candidate,
)
from .server_discovery_registry import (
    _next_low_priority,
    register_discovered_candidate,
    run_discovered_candidate_test,
)
from .server_model_resolve import _is_hailo_vlm_available, _is_ollama_available

__all__ = [
    "discover_local_ollama_endpoints",
    "get_discovered_candidates",
    "ignore_discovered_candidate",
    "load_config_json",
    "match_discovered_candidate",
    "probe_openai_compat_models",
    "register_discovered_candidate",
    "run_discovered_candidate_test",
    "save_config_json",
    "unignore_discovered_candidate",
    "unmatch_discovered_candidate",
    "_cleanup_discovery_metadata",
    "_discover_known_openai_compat_candidates",
    "_discover_local_hailo_candidates",
    "_is_hailo_vlm_available",
    "_is_ollama_available",
    "_is_private_url",
    "_load_discovery_ignored",
    "_load_discovery_matches",
    "_next_low_priority",
    "decrypt",
]
