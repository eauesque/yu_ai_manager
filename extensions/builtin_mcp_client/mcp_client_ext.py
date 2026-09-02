"""builtin-mcp-client Extension entrypoint.

Provides REST API and management UI for connecting to external MCP servers.
"""

from __future__ import annotations

import atexit
import logging
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from quart import Blueprint, jsonify, render_template, request  # noqa: E402

from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from core.web.auth_helpers import require_local as _require_local

from .core_impl.connection_manager import ConnectionManager  # noqa: E402

logger = logging.getLogger(__name__)


def get_blueprint() -> Blueprint:
    bp = Blueprint(
        "ext_mcp_client",
        __name__,
        template_folder="templates",
    )

    mgr = ConnectionManager()


    @bp.record_once
    def _on_register(_state):
        """Auto-connect on startup, register shutdown hook."""
        try:
            mgr.auto_connect_all()
        except Exception:
            logger.warning("MCP client auto-connect failed", exc_info=True)
        atexit.register(mgr.shutdown)

    # ── UI page ─────────────────────────────────────────────────────

    @bp.route("/")
    async def mcp_client_ui():
        return await render_template("mcp_client/mcp_client.html")

    # ── API: list / add ─────────────────────────────────────────────

    @bp.route("/api/connections", methods=["GET"])
    async def api_list_connections():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return jsonify({"ok": True, "connections": mgr.list_connections()})

    @bp.route("/api/connections", methods=["POST"])
    async def api_add_connection():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False, "error": "JSON body required"}), 400
        if data.get("transport") == "stdio":
            local_err = _require_local("MCP stdio connection")
            if local_err:
                return local_err
        saved, err = mgr.add_connection(data)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "connection": saved}), 201

    # ── API: update / delete ────────────────────────────────────────

    @bp.route("/api/connections/<conn_id>", methods=["PUT"])
    async def api_update_connection(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not data:
            return jsonify({"ok": False, "error": "JSON body required"}), 400
        current = mgr.get_connection_config(conn_id)
        if current is None:
            return jsonify({"ok": False, "error": "Connection not found"}), 404
        if data.get("transport", current.get("transport")) == "stdio":
            local_err = _require_local("MCP stdio connection")
            if local_err:
                return local_err
        updated, err = mgr.update_connection(conn_id, data)
        if err:
            code = 404 if "not found" in err.lower() else 400
            return jsonify({"ok": False, "error": err}), code
        return jsonify({"ok": True, "connection": updated})

    @bp.route("/api/connections/<conn_id>", methods=["DELETE"])
    async def api_delete_connection(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        err = mgr.delete_connection(conn_id)
        if err:
            return jsonify({"ok": False, "error": err}), 404
        return jsonify({"ok": True})

    # ── API: connect / disconnect ───────────────────────────────────

    @bp.route("/api/connections/<conn_id>/connect", methods=["POST"])
    async def api_connect(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        saved = mgr.get_connection_config(conn_id)
        if saved and saved.get("transport") == "stdio":
            local_err = _require_local("MCP stdio connection")
            if local_err:
                return local_err
        result = mgr.connect(conn_id)
        code = 200 if result.get("ok") else 502
        return jsonify(result), code

    @bp.route("/api/connections/<conn_id>/disconnect", methods=["POST"])
    async def api_disconnect(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = mgr.disconnect(conn_id)
        return jsonify(result)

    # ── API: tools / call-tool ──────────────────────────────────────

    @bp.route("/api/connections/<conn_id>/tools", methods=["GET"])
    async def api_get_tools(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        tools = mgr.get_tools(conn_id)
        return jsonify({"ok": True, "tools": tools})

    @bp.route("/api/connections/<conn_id>/call-tool", methods=["POST"])
    async def api_call_tool(conn_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True)
        if not data or "name" not in data:
            return jsonify({"ok": False, "error": "name is required"}), 400
        arguments = data.get("arguments")
        if arguments is not None and not isinstance(arguments, dict):
            return jsonify({"ok": False, "error": "arguments must be a dict or null"}), 400
        result = mgr.call_tool(
            conn_id,
            data["name"],
            arguments,
        )
        return jsonify(result)

    return bp


__all__ = ["get_blueprint"]
