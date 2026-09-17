"""Route registration for tools misc/settings/inspect APIs."""

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_params import get_int_arg, get_str_arg
from core.infra_core.api_request import require_json_dict
from core.services_core.db_async import run_db_sync
from core.tools.services_drop_upload import (
    ingest_upload_batch_payload,
    register_path_payload,
    resolve_drop_inbox_dir,
)
from core.tools_api.cache_config_ops import (
    cache_info_payload,
    clear_cache_payload,
    get_config_payload,
    get_toml_config_payload,
    legacy_migration_status_payload,
    migrate_legacy_config_payload,
    rebuild_groups_payload,
    save_config_payload,
    save_toml_config_payload,
)
from core.tools_api.file_ops import file_search_payload, inspect_uploaded_file_payload
from core.tools_api.folder_ops import list_dirs_request_payload, select_folder_payload
from core.web.apikey_auth.key_scopes import key_has_scope
from core.web.auth_restart import snapshot_request_origin


def _require_admin_scope_for_config():
    key_info = getattr(request, "api_key_info", None)
    if key_info and not key_has_scope(key_info, "admin"):
        return api_error("Insufficient scope: requires 'admin'", 403)
    return None


def register_tools_misc_routes(bp):
    """Register folder/cache/search/settings/inspect tool routes."""

    @bp.route("/api/tools/select-folder")
    async def api_select_folder():
        initial_dir = get_str_arg(request.args, ("initial", "path", "dir"), "")
        origin = snapshot_request_origin()
        payload, status = await run_db_sync(select_folder_payload, initial_dir, origin)
        return api_result(payload, status)

    @bp.route("/api/tools/list-dirs")
    async def api_list_dirs():
        raw_path = get_str_arg(request.args, ("path", "dir", "initial"), "")
        origin = snapshot_request_origin()
        payload, status = await run_db_sync(list_dirs_request_payload, raw_path, origin)
        return api_result(payload, status)

    @bp.route("/api/tools/cache-info")
    async def api_cache_info():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(cache_info_payload), 200)

    @bp.route("/api/tools/clear-cache", methods=["POST"])
    async def api_clear_cache():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(clear_cache_payload), 200)

    @bp.route("/api/tools/rebuild-groups", methods=["POST"])
    async def api_rebuild_groups():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(rebuild_groups_payload), 200)

    @bp.route("/api/tools/file-search")
    async def api_file_search():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        query = get_str_arg(request.args, ("q", "query"), "")
        meta_filter = get_str_arg(request.args, ("meta", "meta_filter"), "all")
        limit = get_int_arg(request.args, ("limit", "n", "page_size"), 100, minimum=1, maximum=500)
        payload, status = await run_db_sync(file_search_payload, query, meta_filter, limit)
        return api_result(payload, status)

    @bp.route("/api/settings/config")
    async def api_get_config():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(get_config_payload), 200)

    @bp.route("/api/settings/config", methods=["POST"])
    async def api_save_config():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        payload, status = await run_db_sync(save_config_payload, data)
        return api_result(payload, status)

    @bp.route("/api/settings/config-toml")
    async def api_get_config_toml():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        text, status = await run_db_sync(get_toml_config_payload)
        from quart import Response

        return Response(text, status=status, mimetype="text/plain; charset=utf-8")

    @bp.route("/api/settings/config-toml", methods=["POST"])
    async def api_save_config_toml():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        raw = (await request.get_data()).decode("utf-8")
        payload, status = await run_db_sync(save_toml_config_payload, raw)
        return api_result(payload, status)

    @bp.route("/api/settings/config/legacy-migration")
    async def api_legacy_config_migration_status():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(legacy_migration_status_payload), 200)

    @bp.route("/api/settings/config/legacy-migration", methods=["POST"])
    async def api_migrate_legacy_config():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        return api_result(await run_db_sync(migrate_legacy_config_payload), 200)

    @bp.route("/api/tools/faststart-prescan", methods=["POST"])
    async def api_faststart_prescan():
        """Pre-generate faststart cache for all MP4/MOV files.

        Returns 202 immediately as processing runs in the background.
        """
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        from core.files_core.faststart_prescan import start_faststart_prescan

        started = start_faststart_prescan()
        return api_result(
            {"ok": True, "started": started, "message": "faststart prescan started" if started else "already running"},
            202 if started else 200,
        )

    @bp.route("/api/inspect", methods=["POST"])
    async def api_inspect_file():
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        files = await request.files
        if "file" not in files:
            return api_error("No file uploaded", 400)

        zip_entry = (await request.form).get("zip_entry", "")
        uploaded_file = files["file"]
        payload, status = await run_db_sync(inspect_uploaded_file_payload, uploaded_file, zip_entry)
        return api_result(payload, status)

    @bp.route("/api/dnd-upload", methods=["POST"])
    async def api_dnd_upload():
        """Accept multipart file uploads, save to drop inbox, ingest into library."""
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        from core.configuration.api import load_config

        files_map = await request.files
        uploads = list(files_map.values())
        if not uploads:
            return api_error("No files uploaded", 400)
        config = load_config(None)
        payload, status = await run_db_sync(ingest_upload_batch_payload, uploads, config)
        return api_result(payload, status)

    @bp.route("/api/dnd-inbox", methods=["GET"])
    async def api_dnd_inbox_info():
        """Return the resolved drop inbox directory for the UI to display."""
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err
        from core.configuration.api import load_config

        config = load_config(None)
        inbox, err = resolve_drop_inbox_dir(config)
        if err or inbox is None:
            return api_result(
                {"ok": False, "code": "no_inbox", "error": err or "inbox unresolved"},
                200,
            )
        return api_result(
            {"ok": True, "inbox": str(inbox), "explicit": bool(config.get("drop_inbox_dir"))},
            200,
        )

    @bp.route("/api/files/register-path", methods=["POST"])
    async def api_register_file_path():
        """Register an existing on-disk file by absolute path (MCP-friendly)."""
        auth_err = _require_admin_scope_for_config()
        if auth_err:
            return auth_err

        from core.configuration.api import load_config

        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        raw_path = str((data or {}).get("path") or "")
        config = load_config(None)
        payload, status = await run_db_sync(register_path_payload, raw_path, config)
        return api_result(payload, status)
