"""Hook integration for process-isolated extensions.

Generates proxy callbacks that can register extension hooks
running in isolated processes with the HookRegistry.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from quart import Blueprint, jsonify
from quart import request as flask_request

logger = logging.getLogger(__name__)

from ..extensions_defs import TrustLevel
from ..validation.extension_permissions import get_granted_permission_set
from .process_isolation import IPCError, IsolatedExtensionProcess, get_isolated_process, register_isolated_process


def create_proxy_hook(ext_name: str, hook_name: str) -> Callable:
    """Generate a proxy callback for an isolated process hook.

    Returns a callable for HookRegistry.register().
    Forwards calls to the worker via IPC on invocation.
    """
    def proxy_callback(*args, **kwargs):
        proc = get_isolated_process(ext_name)
        if proc is None or not proc.is_alive():
            logger.warning(f"{ext_name}: 隔離プロセスが利用不可")
            return None

        try:
            return proc.call_hook(hook_name, list(args), kwargs)
        except IPCError as exc:
            logger.error(f"{ext_name}.{hook_name}: IPC エラー: {exc}")
            return None
        except Exception as exc:
            logger.error(f"{ext_name}.{hook_name}: プロキシエラー: {exc}")
            return None

    proxy_callback.__name__ = f"iso_{ext_name}_{hook_name}"
    proxy_callback.__qualname__ = f"iso_{ext_name}_{hook_name}"
    return proxy_callback


def create_proxy_blueprint(ext_name: str, prefix: str) -> Blueprint:
    """Generate a Quart Blueprint that proxies to an isolated process Blueprint.

    Actual HTTP handling is performed in the worker process;
    this proxy forwards requests via IPC.
    """
    safe_name = ext_name.replace("-", "_")
    bp = Blueprint(f"iso_{safe_name}", __name__)

    @bp.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE"])
    @bp.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy_handler(path):
        proc = get_isolated_process(ext_name)
        if proc is None or not proc.is_alive():
            return jsonify({"error": "Extension process not available"}), 503

        try:
            result = proc._rpc_call("blueprint.request", {
                "method": flask_request.method,
                "path": f"/{path}" if path else "/",
                "args": dict(flask_request.args),
                "json": await flask_request.get_json(silent=True),
                "headers": dict(flask_request.headers),
            })
            if isinstance(result, dict):
                status = result.pop("_status", 200)
                return jsonify(result), status
            return jsonify({"result": result})
        except IPCError:
            logger.exception("Isolated extension blueprint IPC failed", extra={"extension": ext_name})
            return jsonify({"error": "Extension process communication failed"}), 502

    return bp


def load_isolated_extension(
    manifest,
    config: dict,
    registry,
    blueprints: list,
) -> bool:
    """Load an extension as an isolated process.

    Returns:
        True: isolated load succeeded
        False: isolated load failed
    """
    granted = get_granted_permission_set(config, manifest.name)
    declared = {
        permission.name
        for group in (manifest.permissions.required, manifest.permissions.optional)
        for permission in group
    } if manifest.permissions else set()
    require_os_isolation = manifest.trust_level != TrustLevel.TRUSTED
    has_db_access = bool({"db:read", "db:write"} & (set(granted) | declared))
    if require_os_isolation and has_db_access and manifest.has_blueprint:
        manifest.status = "error"
        manifest.status_message = "DB-enabled isolated blueprints are unsupported"
        logger.error("%s: DB-enabled isolated blueprint rejected", manifest.name)
        return False

    proc = IsolatedExtensionProcess(
        ext_name=manifest.name,
        ext_dir=manifest.directory,
        entry=manifest.entry,
        granted_permissions=granted,
        config=config,
        require_os_isolation=require_os_isolation,
    )

    if not proc.start():
        manifest.status = "error"
        manifest.status_message = "隔離プロセス起動失敗"
        return False

    register_isolated_process(manifest.name, proc)

    # Register hook proxies
    for hook_name in manifest.hooks:
        proxy = create_proxy_hook(manifest.name, hook_name)
        registry.register(
            hook_name=hook_name,
            extension_name=manifest.name,
            callback=proxy,
            priority=manifest.priority,
        )

    # Register blueprint proxy
    if manifest.has_blueprint:
        prefix = manifest.blueprint_prefix
        if not prefix:
            safe_name = manifest.name.replace("builtin-", "").replace("-", "_")
            prefix = f"/ext/{safe_name}"
        proxy_bp = create_proxy_blueprint(manifest.name, prefix)
        blueprints.append((proxy_bp, prefix))

    manifest.status = "isolated"
    manifest.status_message = f"PID={proc._process.pid}"

    logger.info(
        f"{manifest.name}: 隔離ロード完了 "
        f"(PID={proc._process.pid}, hooks={manifest.hooks})"
    )
    return True
