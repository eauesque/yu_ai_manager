"""Handlers for extensions API routes.

CRUD and marketplace operations live here.
Security-related handlers (permissions, code scan, tokens, integrity,
isolation) are in handlers_security.py and re-exported below.
"""

from quart import request

# Re-export security handlers for backward compatibility
from core.extensions_api.handlers_security import (  # noqa: F401
    approve_extension_permissions,
    get_extension_integrity,
    get_extension_permissions,
    get_extension_tokens,
    get_isolation_status,
    get_os_isolation_status,
    rescan_extension,
    scan_extension_code,
)
from core.extensions_core.extensions_defs import CATEGORY_ORDER
from core.extensions_core.lifecycle.extensions_admin import persist_extension_state
from core.extensions_core.lifecycle.extensions_api_ops import (
    build_config_schema,
    install_extension_from_git,
    update_all_git_extensions,
    update_extension_from_git,
    validate_and_save_config,
)
from core.extensions_core.lifecycle.extensions_api_ops import (
    uninstall_extension as uninstall_extension_op,
)
from core.extensions_core.lifecycle.runtime import HOOK_DEFINITIONS, get_extension_manager
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_params import get_arg, get_str_arg
from core.infra_core.api_request import require_json_dict


def list_extensions():
    mgr = get_extension_manager()
    return api_result({
        "extensions": mgr.list_extensions(),
        "total": len(mgr.manifests),
        "category_order": CATEGORY_ORDER,
    }, 200)


def get_extension(name):
    mgr = get_extension_manager()
    info = mgr.get_extension_info(name)
    if info is None:
        return api_error(f"Extension '{name}' not found", 404)
    return api_result(info, 200)


async def toggle_extension(name):
    mgr = get_extension_manager()
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    enabled = get_arg(data, ("enabled", "on"), None)
    if enabled is None:
        manifest = mgr.manifests.get(name)
        if manifest is None:
            return api_error(f"Extension '{name}' not found", 404)
        enabled = not manifest.enabled
    if not mgr.set_enabled(name, bool(enabled)):
        return api_error(f"Extension '{name}' not found", 404)
    persist_extension_state(name, bool(enabled))
    return api_result({"name": name, "enabled": bool(enabled), "message": f"Extension '{name}' {'enabled' if enabled else 'disabled'}"}, 200)


async def extension_config(name):
    mgr = get_extension_manager()
    manifest = mgr.manifests.get(name)
    if manifest is None:
        return api_error(f"Extension '{name}' not found", 404)
    if request.method == "GET":
        return api_result({"name": name, "config_schema": build_config_schema(manifest, name)}, 200)
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    resp, status = validate_and_save_config(manifest, name, data.get("values", {}))
    return api_result(resp, status)


async def install_extension():
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    git_url = get_str_arg(data, ("url", "git", "repo"), "")
    if not git_url:
        return api_error("URL is required", 400)
    from core.extensions_core.lifecycle.extensions_api_git_helpers import validate_git_url
    url_err = validate_git_url(git_url)
    if url_err:
        return api_error(url_err, 400)
    resp, status = install_extension_from_git(get_extension_manager(), git_url)
    return api_result(resp, status)


def update_extension(name):
    resp, status = update_extension_from_git(get_extension_manager(), name)
    return api_result(resp, status)


def update_all_extensions():
    return api_result(update_all_git_extensions(get_extension_manager()), 200)


def uninstall_extension(name):
    resp, status = uninstall_extension_op(get_extension_manager(), name)
    return api_result(resp, status)


def extension_hooks():
    mgr = get_extension_manager()
    return api_result({"hooks": mgr.get_hook_info(), "definitions": {name: {"mode": mode} for name, mode in HOOK_DEFINITIONS.items()}}, 200)


def marketplace_search():
    """Return marketplace extension listing."""
    query = request.args.get("q", "")
    return _marketplace_search_sync(query)


def _marketplace_search_sync(query: str = ""):
    """Thread-pool friendly: no request context needed."""
    from core.extensions_core.lifecycle.extensions_marketplace import search_index

    mgr = get_extension_manager()
    installed = set(mgr.manifests.keys()) if mgr.manifests else set()
    results = search_index(query=query, installed=installed)
    return api_result({"extensions": results, "total": len(results)}, 200)


def marketplace_refresh():
    """Refresh marketplace cache."""
    from core.extensions_core.lifecycle.extensions_marketplace import clear_cache, fetch_index

    clear_cache()
    extensions = fetch_index(force=True)
    return api_result({"refreshed": True, "total": len(extensions)}, 200)
