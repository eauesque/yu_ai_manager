"""Extension management API routes."""

import json
import logging
from pathlib import Path

from quart import Blueprint, Response, request

from core.extensions_api import handlers as h
from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync

bp = Blueprint("extensions", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local

logger = logging.getLogger(__name__)


@bp.route("/api/tauri-shell/tabs")
async def api_tauri_shell_tabs():
    """Return tabs.json merged with dynamically registered extension tabs.

    Accessible without admin scope — the Tauri shell fetches this on startup
    to build the tab bar. Extensions declare tabs via ``tauri_tab`` in their
    extension.json; enabled extensions with a valid tauri_tab entry are
    inserted into the appropriate category.
    """
    try:
        static_path = (
            Path(__file__).resolve().parent.parent.parent
            / "ui" / "default" / "static" / "tauri_shell" / "tabs.json"
        )
        config: dict = json.loads(static_path.read_text(encoding="utf-8"))
    except Exception:
        config = {"version": 1, "categories": [], "bridgeTargets": {}}

    # Build category index for O(1) lookup
    cat_index: dict[str, list] = {
        cat["id"]: cat.setdefault("tabs", [])
        for cat in config.get("categories", [])
    }

    # Collect tauri_tab declarations from all enabled extensions
    try:
        from core.extensions_core.lifecycle import extensions_manager as _em
        mgr = _em.get_manager()
        for _name, manifest in mgr.manifests.items():
            if not manifest.enabled:
                continue
            tt = manifest.tauri_tab
            if not tt or not tt.get("id") or not tt.get("url"):
                continue
            cat_id = tt.get("category", "")
            tab_entry = {
                "id": tt["id"],
                "labelKey": tt.get("labelKey", f"tauri_shell.tab.{tt['id']}"),
                "url": tt["url"],
                "mount": tt.get("mount", "lazy"),
            }
            if cat_id in cat_index:
                # Avoid duplicates if already present
                existing_ids = {t.get("id") for t in cat_index[cat_id]}
                if tt["id"] not in existing_ids:
                    cat_index[cat_id].append(tab_entry)
    except Exception:
        logger.warning("extension route step failed", exc_info=True)

    return Response(
        json.dumps(config, ensure_ascii=False),
        content_type="application/json",
    )


@bp.route("/api/extensions")
async def api_list_extensions():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.list_extensions)


@bp.route("/api/extensions/<name>")
async def api_get_extension(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.get_extension, name)


@bp.route("/api/extensions/<name>/toggle", methods=["POST"])
async def api_toggle_extension(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await h.toggle_extension(name)


@bp.route("/api/extensions/<name>/config", methods=["GET", "POST"])
async def api_extension_config(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await h.extension_config(name)


@bp.route("/api/extensions/install", methods=["POST"])
async def api_install_extension():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension install")
    if blocked:
        return blocked
    return await h.install_extension()


@bp.route("/api/extensions/<name>/update", methods=["POST"])
async def api_update_extension(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension update")
    if blocked:
        return blocked
    return await run_db_sync(h.update_extension, name)


@bp.route("/api/extensions/update-all", methods=["POST"])
async def api_update_all_extensions():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension update")
    if blocked:
        return blocked
    return await run_db_sync(h.update_all_extensions)


@bp.route("/api/extensions/<name>/uninstall", methods=["DELETE"])
async def api_uninstall_extension(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension uninstall")
    if blocked:
        return blocked
    return await run_db_sync(h.uninstall_extension, name)


@bp.route("/api/extensions/<name>/permissions", methods=["GET", "POST"])
async def api_extension_permissions(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    if request.method == "POST":
        return await h.approve_extension_permissions(name)
    return await run_db_sync(h.get_extension_permissions, name)


@bp.route("/api/extensions/<name>/scan-results")
async def api_extension_scan_results(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.scan_extension_code, name)


@bp.route("/api/extensions/<name>/rescan", methods=["POST"])
async def api_extension_rescan(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.rescan_extension, name)


@bp.route("/api/extensions/<name>/tokens")
async def api_extension_tokens(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.get_extension_tokens, name)


@bp.route("/api/extensions/<name>/integrity")
async def api_extension_integrity(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.get_extension_integrity, name)


@bp.route("/api/extensions/hooks")
async def api_extension_hooks():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.extension_hooks)


@bp.route("/api/extensions/marketplace")
async def api_marketplace_search():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    query = request.args.get("q", "")
    return await run_db_sync(h._marketplace_search_sync, query)


@bp.route("/api/extensions/marketplace/refresh", methods=["POST"])
async def api_marketplace_refresh():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.marketplace_refresh)


@bp.route("/api/extensions/isolation")
async def api_isolation_status():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.get_isolation_status)


@bp.route("/api/extensions/os-isolation")
async def api_os_isolation_status():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    return await run_db_sync(h.get_os_isolation_status)


# --- Extension Authoring (concession model) ---

@bp.route("/api/extensions/author/create", methods=["POST"])
async def api_author_create():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension authoring")
    if blocked:
        return blocked
    from core.extensions_core.authoring import create_extension
    data = await request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    return api_result(create_extension(name, description))


@bp.route("/api/extensions/author/<name>/write", methods=["POST"])
async def api_author_write(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension authoring")
    if blocked:
        return blocked
    from core.extensions_core.authoring import write_extension_file
    data = await request.get_json(force=True, silent=True) or {}
    file_type = (data.get("file_type") or "").strip()
    filename = (data.get("filename") or "").strip()
    content = data.get("content", "")
    return api_result(write_extension_file(name, file_type, filename, content))


@bp.route("/api/extensions/author/<name>/read")
async def api_author_read(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension authoring")
    if blocked:
        return blocked
    from core.extensions_core.authoring import read_extension_file
    file_type = request.args.get("file_type", "").strip()
    filename = request.args.get("filename", "").strip()
    return api_result(read_extension_file(name, file_type, filename))


@bp.route("/api/extensions/author/<name>/files")
async def api_author_list_files(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension authoring")
    if blocked:
        return blocked
    from core.extensions_core.authoring import list_extension_files
    return api_result(list_extension_files(name))


@bp.route("/api/extensions/author/<name>/validate", methods=["POST"])
async def api_author_validate(name):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    blocked = _require_local("Extension authoring")
    if blocked:
        return blocked
    from core.extensions_core.authoring import validate_extension
    return api_result(validate_extension(name))
