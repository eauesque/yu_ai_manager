"""Entry point: python -m mcp_server"""

import contextlib
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap app state so action_journal can write to the SQLite DB.
#
# When run as a stdio subprocess (``python -m mcp_server``), the web-server
# bootstrap that normally calls init_app_state() / register_core_services()
# is not executed.  We do the minimal init here so that:
#   - action_journal.record_action() can persist tool calls
#   - circuit_breaker.record() can update in-process state
#
# DB path resolution priority (mirrors Web Server's runtime_runner.py chain,
# minus the --db CLI arg which is only available to the Web Server):
#
#   1. config.json "db" field  — Settings > Change DB persists here
#   2. TAGDB_DB env var        — same name as Web Server uses
#   3. YU_DB_PATH env var      — legacy alias kept for backward compat
#   4. <repo_root>/data/tags.db — dev default (matches Web Server default)
# ---------------------------------------------------------------------------

_repo_root = Path(__file__).resolve().parent.parent

# Identify this process to the shared_state module so it writes to the "mcp" row.
# Must be set before any core.agent_safety.* import.
os.environ.setdefault("YU_PROCESS_ID", "mcp")


def _resolve_db_path() -> Path:
    """Return the DB path using the same priority chain as the Web Server."""
    default_db = _repo_root / "data" / "tags.db"

    # 1. Config "db" field (Settings > Change DB writes here)
    # A malformed config falls through to the env vars below, by design.
    with contextlib.suppress(Exception):
        from core.configuration.json_rw import candidate_config_paths, load_config_json
        cfg_path = next((_repo_root / path for path in candidate_config_paths() if (_repo_root / path).exists()), None)
        if cfg_path:
            cfg = load_config_json(str(cfg_path))
            if cfg_db := cfg.get("db"):
                return Path(cfg_db)

    # 2. TAGDB_DB — the env var the Web Server also reads
    if tagdb := os.environ.get("TAGDB_DB"):
        return Path(tagdb)

    # 3. YU_DB_PATH — legacy alias (kept for backward compatibility)
    if yu_db := os.environ.get("YU_DB_PATH"):
        return Path(yu_db)

    # 4. Default: data/tags.db relative to repo root
    return default_db


_db_path = _resolve_db_path()

try:
    from core.services_core.app_runtime_state import DB_PATH as _existing_db_path
    if _existing_db_path is None:
        from core.services_core.app_runtime_state import init_app_state
        init_app_state(_db_path, {})
except Exception as _e:  # pragma: no cover
    print(f"[mcp_server] Warning: could not init app state: {_e}", file=sys.stderr)

try:
    from core.extensions_core.service_registry_core_services import register_core_services
    register_core_services(db_path=_db_path)
except Exception as _e:  # pragma: no cover
    print(f"[mcp_server] Warning: could not register core services: {_e}", file=sys.stderr)

# ---------------------------------------------------------------------------

from .server import mcp  # noqa: E402 (must be after app_state init above)

_base_url = os.environ.get("YU_BASE_URL", "http://localhost:5000")
_api_key = os.environ.get("YU_API_KEY", "")

print("YU AI Manager MCP Server", file=sys.stderr)
print(f"  Base URL: {_base_url}", file=sys.stderr)
print(f"  API Key:  {'configured' if _api_key else 'none (using session auth)'}", file=sys.stderr)
print(f"  DB path:  {_db_path}", file=sys.stderr)

mcp.run(transport="stdio")
