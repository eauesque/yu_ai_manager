"""Quart routes for sweep-axis files (Bridge Prompt S/R wildcard expansion)."""

from __future__ import annotations

import logging

from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)
from quart import jsonify, render_template, request

from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from .sweep_axis_loader import load_sweep_axes
from .wildcard_loader import validate_dirs

logger = logging.getLogger(__name__)
EXT_NAME = "builtin-prompt-simulator"


def _read_axis_settings() -> tuple[list[str], bool, list[str]]:
    axis_dirs = get_extension_config_value(EXT_NAME, "sweep_axis_dirs", []) or []
    include_wc = bool(
        get_extension_config_value(EXT_NAME, "sweep_include_wildcard_dirs", False)
    )
    wildcard_dirs = get_extension_config_value(EXT_NAME, "wildcard_dirs", []) or []
    return axis_dirs, include_wc, wildcard_dirs


def register_sweep_axis_routes(bp):
    @bp.route("/sweep-axes-manager", methods=["GET"])
    async def sweep_axes_manager_page():
        return await render_template("sweep_axes_manager.html")

    @bp.route("/sweep-axes", methods=["GET"])
    async def api_get_sweep_axes():
        # If a browser hits this URL directly, send the user to the manager UI
        # instead of dumping raw JSON. JS callers either set Accept or pass
        # ?json=1 to force the API response.
        accept = (request.headers.get("Accept") or "").lower()
        wants_json = "application/json" in accept or request.args.get("json") in (
            "1", "true", "yes",
        )
        is_xhr = request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
        if "text/html" in accept and not wants_json and not is_xhr:
            from quart import redirect
            return redirect("/ext/prompt-sim/sweep-axes-manager", code=302)

        # Bridge sweep loaders read this on demand; require an admin scope
        # so only the local UI (post-login) can enumerate axis values.
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        axis_dirs, include_wc, wildcard_dirs = _read_axis_settings()
        if not axis_dirs and not (include_wc and wildcard_dirs):
            return jsonify(
                {
                    "axes": {},
                    "sources": {},
                    "axis_dirs": axis_dirs,
                    "include_wildcard_dirs": include_wc,
                    "wildcard_dirs": wildcard_dirs,
                }
            )
        try:
            axes, sources = load_sweep_axes(
                axis_dirs,
                include_wildcard_dirs=include_wc,
                wildcard_dirs=wildcard_dirs,
            )
            return jsonify(
                {
                    "axes": axes,
                    "sources": sources,
                    "axis_dirs": axis_dirs,
                    "include_wildcard_dirs": include_wc,
                    "wildcard_dirs": wildcard_dirs,
                }
            )
        except Exception:
            logger.exception("Sweep axis load failed")
            return jsonify({"error": "Sweep axis loading failed"}), 500

    @bp.route("/sweep-axis-config", methods=["POST"])
    async def api_save_sweep_axis_config():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        updates: dict[str, object] = {}
        if "axis_dirs" in data:
            dirs = data.get("axis_dirs")
            if not isinstance(dirs, list):
                return jsonify({"error": "axis_dirs must be a list"}), 400
            cleaned = [
                item.strip()
                for item in dirs
                if isinstance(item, str) and item.strip()
            ]
            updates["sweep_axis_dirs"] = cleaned
        if "include_wildcard_dirs" in data:
            updates["sweep_include_wildcard_dirs"] = bool(
                data.get("include_wildcard_dirs")
            )
        if not updates:
            return jsonify({"error": "no settings provided"}), 400
        save_extension_config_values(EXT_NAME, updates)

        axis_dirs, include_wc, wildcard_dirs = _read_axis_settings()
        return jsonify(
            {
                "axis_dirs": axis_dirs,
                "include_wildcard_dirs": include_wc,
                "validation": validate_dirs(axis_dirs),
            }
        )
