import logging

from quart import Quart, request

logger = logging.getLogger(__name__)

from core.configuration.profiles import list_profiles, touch_last_used, validate_profile_name
from core.infra_core.api_errors import api_error, api_result, api_success
from core.infra_core.api_params import get_str_arg
from core.infra_core.api_request import require_json_dict
from core.web.restart_route_helpers import (
    apply_restart_config_changes,
    check_profile_switch_auth,
    check_remote_restart_access,
    check_restart_auth,
    drop_flag_arg,
    enforce_restart_cooldown,
    get_restart_exec_args,
    launch_restart,
    sanitize_profile_name,
)


def register_restart_route(app: Quart):
    @app.route('/api/server/restart', methods=['POST'])
    async def api_server_restart():
        auth_err = check_restart_auth(app)
        if auth_err:
            return auth_err

        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        confirm = get_str_arg(data, ("confirm", "action", "cmd"), "")
        if confirm != "restart":
            return api_error("confirm='restart' が必要です", 400, code="confirm_required")

        remote_err = check_remote_restart_access(app, data)
        if remote_err:
            return remote_err

        now, cooldown_err = enforce_restart_cooldown()
        if cooldown_err:
            return cooldown_err

        exec_args = get_restart_exec_args(app)
        if not exec_args:
            return api_error("再起動コマンドが未設定です", 500, code="restart_args_missing")

        launch_restart(exec_args, now, "server")
        return api_success(
            {
                "accepted": True,
                "message": "再起動を受け付けました。数秒後に切断されます。",
                "code": "restart_accepted",
            },
            200,
        )

    @app.route('/api/server/restart-with-config', methods=['POST'])
    async def api_restart_with_config():
        """Save config changes and restart the server in one atomic operation.

        Accepts: { "changes": { "key": value, ... }, "confirm": "restart" }
        Supported change keys: "ui", "db" (string paths/names).
        """
        auth_err = check_restart_auth(app)
        if auth_err:
            return auth_err

        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        confirm = get_str_arg(data, ("confirm",), "")
        save_only = confirm == "save_only"
        if confirm not in ("restart", "save_only"):
            return api_error("confirm='restart' または 'save_only' が必要です", 400, code="confirm_required")

        changes = data.get("changes")
        if not isinstance(changes, dict) or not changes:
            return api_error("changes が必要です", 400, code="changes_required")

        remote_err = check_remote_restart_access(app, data)
        if remote_err:
            return remote_err

        now, cooldown_err = enforce_restart_cooldown()
        if cooldown_err:
            return cooldown_err

        applied, apply_err = apply_restart_config_changes(changes)
        if apply_err:
            return apply_err

        # save_only mode: just save config, don't restart (Tauri manages restart)
        if save_only:
            return api_success(
                {
                    "accepted": True,
                    "applied": applied,
                    "message": "設定を保存しました。",
                    "code": "config_saved",
                },
                200,
            )

        # Build exec args, injecting --db override if changed
        exec_args = get_restart_exec_args(app)
        if not exec_args:
            return api_error("再起動コマンドが未設定です", 500, code="restart_args_missing")
        if "db" in applied:
            exec_args = drop_flag_arg(exec_args, "--db") + ["--db", applied["db"]]

        launch_restart(exec_args, now, "config")
        return api_success(
            {
                "accepted": True,
                "applied": applied,
                "message": "設定を保存して再起動します。数秒後に切断されます。",
                "code": "config_restart_accepted",
            },
            200,
        )

    @app.route('/api/server/switch-profile', methods=['POST'])
    async def api_switch_profile():
        auth_err = check_profile_switch_auth(app)
        if auth_err:
            return auth_err

        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])

        target = sanitize_profile_name(data.get("profile", ""))
        confirm = data.get("confirm", "")
        if confirm != "switch":
            return api_error("confirm='switch' が必要です", 400, code="confirm_required")
        if validate_profile_name(target):
            return api_error("プロファイル名が不正です", 400, code="invalid_profile_name")

        profiles = {p["name"]: p for p in list_profiles()}
        if not profiles:
            return api_error("プロファイルが設定されていません", 400, code="no_profiles")
        if target not in profiles:
            return api_error(f"プロファイル '{target}' が見つかりません", 404, code="profile_not_found")
        if target == app.config.get("ACTIVE_PROFILE"):
            return api_error("既にこのプロファイルです", 400, code="already_active")

        now, cooldown_err = enforce_restart_cooldown()
        if cooldown_err:
            return cooldown_err

        # Update active_profile in config.json and touch last_used
        from core.configuration.json_rw import load_config_json, save_config_json
        cfg = load_config_json(None)
        cfg["active_profile"] = target
        save_config_json(cfg)
        touch_last_used(target)

        exec_args = get_restart_exec_args(app)
        if not exec_args:
            return api_error("再起動コマンドが未設定です", 500, code="restart_args_missing")

        launch_restart(drop_flag_arg(exec_args, "--profile"), now, "profile switch")
        label = profiles[target].get("label", target)
        return api_success(
            {
                "accepted": True,
                "message": f"プロファイル '{label}' に切り替えます。数秒後に再起動します。",
                "code": "profile_switch_accepted",
                "profile": target,
            },
            200,
        )
