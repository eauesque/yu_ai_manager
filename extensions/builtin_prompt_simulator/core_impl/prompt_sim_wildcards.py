"""Wildcard route registration for prompt simulator."""

from __future__ import annotations

import logging

from core.extensions_core.extensions_admin import get_extension_config_value, save_extension_config_values
from quart import jsonify, request

from core.infra_core.upload_limits import read_upload_bytes_limited

from .wildcard_loader import (
    delete_wildcard_files,
    load_wildcards_from_dirs,
    load_wildcards_from_zip,
    rename_wildcard_files,
    save_wildcard_file,
    validate_dirs,
)

logger = logging.getLogger(__name__)
EXT_NAME = "builtin-prompt-simulator"
_MAX_WILDCARD_ZIP_BYTES = 50 * 1024 * 1024


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_wildcard_routes(bp):
    @bp.route("/wildcards", methods=["GET"])
    async def api_get_wildcards():
        # If a browser hits this URL directly (e.g. typed in the address bar),
        # send them to the manager UI instead of dumping raw JSON to the page.
        # API consumers should request application/json explicitly or supply the
        # ?raw=1 / ?json=1 query flag to bypass this redirect.
        accept = (request.headers.get("Accept") or "").lower()
        wants_json = "application/json" in accept or request.args.get("json") in ("1", "true", "yes")
        is_xhr = request.headers.get("X-Requested-With", "").lower() == "xmlhttprequest"
        if "text/html" in accept and not wants_json and not is_xhr:
            from quart import redirect
            return redirect("/ext/prompt-sim/manager", code=302)

        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        dirs = get_extension_config_value(EXT_NAME, "wildcard_dirs", [])
        raw = request.args.get("raw") in ("1", "true", "yes")
        if not dirs:
            return jsonify({"wildcards": {}, "dirs": []})
        try:
            wildcards, sources = load_wildcards_from_dirs(dirs, raw=raw)
            return jsonify({"wildcards": wildcards, "sources": sources, "dirs": dirs})
        except Exception:
            logger.exception("Prompt simulator wildcard load failed")
            return jsonify({"error": "Wildcard loading failed"}), 500

    @bp.route("/load-wildcards-zip", methods=["POST"])
    async def api_load_wildcards_zip():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        files = await request.files
        if "file" not in files:
            return jsonify({"error": "No file uploaded"}), 400
        try:
            data = read_upload_bytes_limited(
                files["file"],
                max_bytes=_MAX_WILDCARD_ZIP_BYTES,
            )
            return jsonify({"wildcards": load_wildcards_from_zip(data)})
        except ValueError:
            return jsonify({"error": "File too large (max 50MB)"}), 400
        except Exception:
            logger.exception("Prompt simulator wildcard ZIP load failed")
            return jsonify({"error": "Wildcard ZIP loading failed"}), 500

    @bp.route("/wildcard-file", methods=["POST"])
    async def api_save_wildcard_file():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        name = data.get("name")
        lines = data.get("lines")
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "name is required"}), 400
        if not isinstance(lines, list):
            return jsonify({"error": "lines must be a list"}), 400
        if len(lines) > 100000:
            return jsonify({"error": "Too many lines (max 100000)"}), 400
        for line in lines:
            if not isinstance(line, str):
                return jsonify({"error": "lines must be a list of strings"}), 400
            if len(line) > 8192:
                return jsonify({"error": "Line too long (max 8192 chars)"}), 400

        dirs = get_extension_config_value(EXT_NAME, "wildcard_dirs", [])
        if not dirs:
            return jsonify({"error": "No wildcard directories configured", "code": "no_dirs"}), 400
        try:
            return jsonify({"saved_path": save_wildcard_file(name, lines, dirs)})
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid"}), 400
        except OSError:
            logger.exception("Prompt simulator wildcard file write failed")
            return jsonify({"error": "Failed to write wildcard file", "code": "io_error"}), 500
        except Exception:
            logger.exception("Prompt simulator wildcard save failed")
            return jsonify({"error": "Wildcard save failed"}), 500

    @bp.route("/wildcard-rename", methods=["POST"])
    async def api_rename_wildcard():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        old_name = data.get("old_name")
        new_name = data.get("new_name")
        if not isinstance(old_name, str) or not old_name.strip():
            return jsonify({"error": "old_name is required"}), 400
        if not isinstance(new_name, str) or not new_name.strip():
            return jsonify({"error": "new_name is required"}), 400
        if old_name == new_name:
            return jsonify({"error": "old_name and new_name are identical"}), 400

        dirs = get_extension_config_value(EXT_NAME, "wildcard_dirs", [])
        if not dirs:
            return jsonify({"error": "No wildcard directories configured", "code": "no_dirs"}), 400
        try:
            results = rename_wildcard_files(old_name, new_name, dirs)
        except ValueError as exc:
            msg = str(exc)
            code = "collision" if "already exists" in msg else ("not_found" if "not found" in msg else "invalid")
            status = 409 if code == "collision" else (404 if code == "not_found" else 400)
            return jsonify({"error": msg, "code": code}), status
        except OSError:
            logger.exception("Prompt simulator wildcard rename failed")
            return jsonify({"error": "Failed to rename wildcard file", "code": "io_error"}), 500
        except Exception:
            logger.exception("Prompt simulator wildcard rename failed")
            return jsonify({"error": "Wildcard rename failed"}), 500
        return jsonify({"renamed": results})

    @bp.route("/wildcard-delete", methods=["POST"])
    async def api_delete_wildcard():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "name is required"}), 400

        dirs = get_extension_config_value(EXT_NAME, "wildcard_dirs", [])
        if not dirs:
            return jsonify({"error": "No wildcard directories configured", "code": "no_dirs"}), 400
        try:
            removed = delete_wildcard_files(name, dirs)
        except ValueError as exc:
            msg = str(exc)
            code = "not_found" if "not found" in msg else "invalid"
            status = 404 if code == "not_found" else 400
            return jsonify({"error": msg, "code": code}), status
        except OSError:
            logger.exception("Prompt simulator wildcard delete failed")
            return jsonify({"error": "Failed to delete wildcard file", "code": "io_error"}), 500
        except Exception:
            logger.exception("Prompt simulator wildcard delete failed")
            return jsonify({"error": "Wildcard delete failed"}), 500
        return jsonify({"removed": removed})

    @bp.route("/wildcard-dirs", methods=["POST"])
    async def api_save_wildcard_dirs():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data = await request.get_json(silent=True) or {}
        dirs = data.get("dirs")
        if not isinstance(dirs, list):
            return jsonify({"error": "dirs must be a list"}), 400
        dirs = [item.strip() for item in dirs if isinstance(item, str) and item.strip()]
        save_extension_config_values(EXT_NAME, {"wildcard_dirs": dirs})
        return jsonify({"saved": dirs, "validation": validate_dirs(dirs)})
