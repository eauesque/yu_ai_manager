"""Helper functions for restart-related routes."""

import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from quart import session

from core.configuration.api import validate_profile_db_path
from core.infra_core.api_errors import api_error

from .auth_core import (
    has_remote_restart_token,
    is_local_request,
    is_remote_restart_authorized,
    restart_state,
)

logger = logging.getLogger(__name__)


def sanitize_profile_name(raw: str) -> str:
    """Sanitize profile name for safe use in logs and error messages."""
    return re.sub(r"[\x00-\x1f\x7f]", "", raw.strip()[:64])


def check_restart_auth(app):
    """Shared restart authentication check."""
    if not app.config.get("RESTART_ENV_ENABLED"):
        return api_error(
            "再起動APIは無効です",
            403,
            code="restart_disabled",
            hint="TAGDB_ALLOW_RESTART=1 / --allow-restart / config.server.allow_restart=true のいずれかで有効化してください",
        )

    has_pin = app.config.get("PIN_AUTH")
    if has_pin:
        if not session.get("pin_ok"):
            return api_error("再起動にはPIN認証済みセッションが必要です", 401, code="pin_auth_required")
    elif not is_local_request():
        return api_error("PIN認証が無効のためリモートからの再起動は許可されていません", 403, code="pin_required")
    return None


def check_remote_restart_access(app, data: dict[str, Any]):
    """Validate remote restart access when the request is not local."""
    if is_local_request():
        return None
    if not app.config.get("RESTART_REMOTE_ALLOWED"):
        return api_error("再起動はローカル接続からのみ許可されています", 403, code="local_only")
    if not has_remote_restart_token():
        return api_error(
            "リモート再起動トークンが未設定です",
            403,
            code="remote_token_missing",
            hint="TAGDB_RESTART_TOKEN / --restart-token / config.server.restart_token のいずれかで設定してください",
        )
    if not is_remote_restart_authorized(data):
        return api_error("リモート再起動トークンが不正です", 401, code="remote_token_invalid")
    return None


def check_profile_switch_auth(app):
    """Profile switching requires local access or a PIN-authenticated session."""
    if not is_local_request() and not app.config.get("PIN_AUTH"):
        return api_error("プロファイル切替にはPIN認証が必要です。--pin を設定してください", 403, code="pin_required")
    if app.config.get("PIN_AUTH") and not session.get("pin_ok"):
        return api_error("認証が必要です", 401, code="pin_auth_required")
    return None


def enforce_restart_cooldown(cooldown_sec: int = 20):
    """Return a cooldown error if a restart was recently requested."""
    now = time.time()
    if restart_state["in_progress"] or (now - restart_state["last_requested_at"] < cooldown_sec):
        remaining = max(1, int(cooldown_sec - (now - restart_state["last_requested_at"])))
        return None, api_error(
            f"再起動要求のクールダウン中です（{remaining}秒）",
            429,
            code="restart_cooldown",
        )
    return now, None


def get_restart_exec_args(app) -> list[str] | None:
    exec_args = app.config.get("RESTART_EXEC_ARGS") or [sys.executable, *sys.argv]
    if not isinstance(exec_args, list) or not exec_args:
        return None
    return list(exec_args)


def drop_flag_arg(exec_args: list[str], flag: str) -> list[str]:
    filtered: list[str] = []
    skip_next = False
    for arg in exec_args:
        if skip_next:
            skip_next = False
            continue
        if arg == flag:
            skip_next = True
            continue
        if arg.startswith(f"{flag}="):
            continue
        filtered.append(arg)
    return filtered


def launch_restart(exec_args: list[str], now: float, log_prefix: str) -> None:
    """Kick off the restart worker and mark the shared restart state."""
    restart_state["in_progress"] = True
    restart_state["last_requested_at"] = now

    def _restart_worker():
        try:
            time.sleep(0.8)
            from core.platform import exec_restart

            exec_restart(exec_args)
        except Exception as exc:
            restart_state["in_progress"] = False
            logger.error("%s restart failed: %s: %s", log_prefix, type(exc).__name__, exc)

    threading.Thread(target=_restart_worker, daemon=True).start()


def apply_restart_config_changes(changes: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """Validate and apply allowed config changes."""
    from core.configuration.json_rw import load_config_json, save_config_json

    allowed_keys = {"ui", "db"}
    unknown = set(changes.keys()) - allowed_keys
    if unknown:
        return {}, api_error(f"不明な変更キー: {', '.join(unknown)}", 400, code="invalid_change_key")

    cfg = load_config_json(None)
    applied: dict[str, Any] = {}

    if "ui" in changes:
        ui_name = str(changes["ui"]).strip()
        if not ui_name or not re.match(r"^[a-zA-Z0-9_-]+$", ui_name):
            return {}, api_error("UI名が不正です", 400, code="invalid_ui_name")
        cfg["ui"] = ui_name
        applied["ui"] = ui_name

    if "db" in changes:
        db_val = re.sub(r"[\x00-\x1f\x7f]", "", str(changes["db"]).strip())
        if not db_val:
            return {}, api_error("DBパスが空です", 400, code="empty_db_path")
        try:
            validate_profile_db_path(db_val)
        except ValueError:
            logger.exception("Invalid restart DB path change requested")
            return {}, api_error("DB path is invalid", 400, code="invalid_db_path")
        cfg["db"] = db_val
        applied["db"] = db_val
        Path(db_val).parent.mkdir(parents=True, exist_ok=True)

    save_config_json(cfg)
    return applied, None
