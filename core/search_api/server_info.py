"""Server info response builder."""

import logging
import threading
import time
from pathlib import Path

from core.configuration.api import load_config_json
from core.configuration.profiles import list_profiles
from core.platform.detect import platform_display_name
from core.search_api.utils import get_lan_ips
from core.services_core.db_api import (
    get_db_path,
    get_readonly_db,
    get_start_time,
    get_startup_migration_info,
    get_startup_status,
    is_boot_ready,
)
from core.services_core.db_meta import get_meta_int, get_meta_json
from core.ui_core import resolve_active_ui
from core.ui_core.manager import list_uis

logger = logging.getLogger(__name__)

_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"

# Human-readable labels and hints for each restart blocker code
RESTART_BLOCKER_LABELS: dict[str, dict[str, str]] = {
    "restart_disabled": {
        "label": "再起動が無効",
        "description": "サーバーの再起動機能が無効化されています。",
        "hint": "TAGDB_ALLOW_RESTART=1 または --allow-restart オプションで有効化してください。",
    },
    "pin_not_active": {
        "label": "PIN未設定（リモート接続）",
        "description": "リモートからの再起動にはPIN認証が必要です。",
        "hint": "Settings > Server タブ > PIN認証コードに数字を入力してください。",
    },
    "local_only": {
        "label": "ローカル接続のみ許可",
        "description": "リモートからの再起動は許可されていません。",
        "hint": "TAGDB_RESTART_REMOTE=1 または --restart-remote で有効化してください。",
    },
    "remote_token_missing": {
        "label": "リモートトークン未設定",
        "description": "リモート再起動トークンが設定されていません。",
        "hint": "TAGDB_RESTART_TOKEN=<token> または --restart-token で設定してください。",
    },
    "pin_session_required": {
        "label": "PIN認証が必要",
        "description": "再起動にはPINセッションが必要です。",
        "hint": "画面右上の鍵アイコンからPINを入力してください。",
    },
}


def _detect_system_timezone() -> str:
    from core.timezone_core.tz_helper import detect_system_timezone  # noqa: PLC0415
    return detect_system_timezone()


def _read_version() -> str:
    try:
        return "v" + _VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "v0.0.0"


APP_VERSION = _read_version()

# --- DB stats cache (TTL 180s) ---
# Long TTL to minimize COUNT(*) + GROUP BY cost on 280K files
_stats_cache: dict = {}
_stats_cache_ts: float = 0
_stats_refresh_pending = False
_stats_lock = threading.Lock()
_STATS_TTL = 180


def invalidate_stats_cache() -> None:
    """Clear the DB stats cache so the next request fetches fresh data."""
    global _stats_cache, _stats_cache_ts
    with _stats_lock:
        _stats_cache = {}
        _stats_cache_ts = 0


def mark_stats_refresh_pending() -> None:
    """Avoid caching stale persisted stats while post-scan refresh is pending."""
    global _stats_cache, _stats_cache_ts, _stats_refresh_pending
    with _stats_lock:
        _stats_cache = {}
        _stats_cache_ts = 0
        _stats_refresh_pending = True


def mark_stats_refresh_complete() -> None:
    """Allow persisted stats to be used after the refresh attempt finishes."""
    global _stats_cache, _stats_cache_ts, _stats_refresh_pending
    with _stats_lock:
        _stats_cache = {}
        _stats_cache_ts = 0
        _stats_refresh_pending = False


def _get_db_stats(con) -> dict:
    """Get file_count, tag_count, schema_version, and meta_stats with TTL caching."""
    global _stats_cache, _stats_cache_ts
    now = time.time()
    with _stats_lock:
        if _stats_cache and now - _stats_cache_ts < _STATS_TTL:
            return _stats_cache
        refresh_pending = _stats_refresh_pending

    meta_stats = get_meta_json(con, "meta_stats") if not refresh_pending else None
    if meta_stats is not None:
        file_count = get_meta_int(con, "total_files", -1)
        tag_count = get_meta_int(con, "tag_count", -1)
        schema_version = get_meta_int(con, "schema_version", -1)
        if file_count >= 0 and tag_count >= 0 and schema_version >= 0:
            result = {
                "file_count": file_count,
                "tag_count": tag_count,
                "schema_version": schema_version,
                "meta_stats": meta_stats,
            }
            with _stats_lock:
                _stats_cache = result
                _stats_cache_ts = now
            return result

    tag_count = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    schema_version = con.execute(
        "SELECT MAX(version) FROM schema_version"
    ).fetchone()[0]
    meta_stats = {}
    for row in con.execute(
        "SELECT COALESCE(meta_source,'unknown') as ms, COUNT(*) as c "
        "FROM files WHERE is_deleted=0 GROUP BY ms ORDER BY c DESC"
    ).fetchall():
        meta_stats[row[0]] = row[1]

    # Use meta_stats sum as authoritative file count (already computed above)
    file_count = sum(meta_stats.values())

    result = {
        "file_count": file_count,
        "tag_count": tag_count,
        "schema_version": schema_version,
        "meta_stats": meta_stats,
    }
    with _stats_lock:
        _stats_cache = result
        _stats_cache_ts = now
    return result


def _approx_file_count(con) -> int | None:
    """Retrieve approximate row count for the files table from sqlite_stat1."""
    try:
        row = con.execute(
            "SELECT stat FROM sqlite_stat1 WHERE tbl='files' AND idx='idx_files_deleted_mtime' LIMIT 1"
        ).fetchone()
        if row and row[0]:
            parts = row[0].split()
            if parts:
                return int(parts[0])
    except Exception:
        logger.debug("search step failed", exc_info=True)
    return None


def build_server_info_response(app_config, session_obj, local_only_ok: bool, host: str):
    con = get_readonly_db()
    stats = _get_db_stats(con)
    file_count = stats["file_count"]
    tag_count = stats["tag_count"]
    schema_version = stats["schema_version"]
    meta_stats = stats["meta_stats"]
    db_size_bytes = get_db_path().stat().st_size if get_db_path().exists() else 0
    db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
    uptime_seconds = int(time.time() - get_start_time())
    lan_ips = get_lan_ips()

    has_pin = bool(app_config.get("PIN_AUTH"))
    pin_source = app_config.get("PIN_SOURCE", "none")
    restart_enabled = bool(app_config.get("RESTART_ENV_ENABLED"))
    restart_source = app_config.get("RESTART_ENABLE_SOURCE", "none")
    restart_remote_allowed = bool(app_config.get("RESTART_REMOTE_ALLOWED"))
    restart_remote_source = app_config.get("RESTART_REMOTE_SOURCE", "none")
    restart_remote_token_set = bool(str(app_config.get("RESTART_REMOTE_TOKEN") or "").strip())
    restart_remote_token_source = app_config.get("RESTART_REMOTE_TOKEN_SOURCE", "none")
    cfg = load_config_json(None)
    cfg_server = cfg.get("server", {}) if isinstance(cfg, dict) else {}
    config_pin_raw = cfg_server.get("pin")
    config_has_pin = bool(str(config_pin_raw).strip()) if config_pin_raw is not None else False

    pin_session_ok = bool(session_obj.get("pin_ok"))
    restart_blockers = []
    if not restart_enabled:
        restart_blockers.append("restart_disabled")
    # PIN is only required for remote requests; local requests can restart without PIN
    if not has_pin and not local_only_ok:
        restart_blockers.append("pin_not_active")
    if not local_only_ok and not restart_remote_allowed:
        restart_blockers.append("local_only")
    if not local_only_ok and restart_remote_allowed and not restart_remote_token_set:
        restart_blockers.append("remote_token_missing")
    if has_pin and not pin_session_ok:
        restart_blockers.append("pin_session_required")

    timezone_value = cfg.get("timezone") if isinstance(cfg, dict) else None

    # UI info
    active_ui = resolve_active_ui(cfg if isinstance(cfg, dict) else {})
    try:
        available_uis = [
            {
                "name": u["name"],
                "label": u["manifest"].get("label") or u["name"],
                "is_sample": bool(u["manifest"].get("is_sample", False)),
            }
            for u in list_uis()
        ]
    except Exception:
        available_uis = [{"name": active_ui, "label": active_ui, "is_sample": False}]

    info = {
        "timezone": timezone_value or _detect_system_timezone(),
        "timezone_source": "config" if timezone_value else "system",
        "active_ui": active_ui,
        "available_uis": available_uis,
        "boot_state": "ready" if is_boot_ready() else "booting",
        "file_count": file_count,
        "tag_count": tag_count,
        "schema_version": schema_version,
        "meta_stats": meta_stats,
        "version": APP_VERSION,
        "uptime_seconds": uptime_seconds,
        "has_pin": has_pin,
        "config_has_pin": config_has_pin,
        "is_local_request": local_only_ok,
        "restart_available_now": len(restart_blockers) == 0,
        "restart_blockers": restart_blockers,
        "restart_blocker_details": [
            RESTART_BLOCKER_LABELS.get(code, {"label": code, "description": "", "hint": ""})
            | {"code": code}
            for code in restart_blockers
        ],
        "restart_requires": {
            "pin_auth": True,
            "confirm_token": True,
            "remote_token_if_remote": True,
        },
        "server_mode": app_config.get("SERVER_MODE", "full"),
        "startup_migration": get_startup_migration_info(),
        "startup_status": get_startup_status(),
        "active_profile": app_config.get("ACTIVE_PROFILE"),
        "profiles": [
            {
                "name": p["name"],
                "label": p.get("label", p["name"]),
                "description": p.get("description", ""),
                "favorite": p.get("favorite", False),
                "last_used_at": p.get("last_used_at"),
            }
            for p in list_profiles()
        ],
    }

    # Non-sensitive stats: always expose
    info.update({
        "db_size_mb": db_size_mb,
        "platform": platform_display_name(),
        "lan_ips": lan_ips,
    })

    # Expose sensitive server details only to local requests
    if local_only_ok:
        info.update({
            "db_path": str(get_db_path()),
            "host": host,
            "pin_source": pin_source,
            "restart_enabled": restart_enabled,
            "restart_enable_source": restart_source,
            "restart_remote_allowed": restart_remote_allowed,
            "restart_remote_source": restart_remote_source,
            "restart_remote_token_set": restart_remote_token_set,
            "restart_remote_token_source": restart_remote_token_source,
            # Local-only: the build log's lines carry local crate and path
            # names. A failure here must not cost the whole response -- this
            # is a progress readout, not part of the server's own state.
            "fast_mode_build": _fast_mode_build_status(),
        })

    return info


def _fast_mode_build_status():
    try:
        from core.search_api.fast_mode_status import fast_mode_build_status

        return fast_mode_build_status()
    except Exception:  # noqa: BLE001 -- a progress readout never breaks server-info
        return None
