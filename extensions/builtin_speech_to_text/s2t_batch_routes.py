"""Speech-to-Text batch transcription routes.

Input modes (exclusive, specify exactly one):
  1. file_ids   - File ID list (legacy, max 500)
  2. directory  - Directory path (auto-detect video/audio files)
  3. list_file  - Text/CSV file path (one file path per line)

NOTE: Resolvers and batch worker have been moved to s2t_batch_resolvers.py.
This module re-exports all public symbols for backward compatibility.
"""

import logging
import threading

from quart import jsonify, request

from .s2t_batch_resolvers import (  # noqa: F401 -- re-export
    get_default_language,
    resolve_directory,
    resolve_list_file,
    run_batch,
)

logger = logging.getLogger(__name__)

_EXT_NAME = "builtin-speech-to-text"
_BATCH_MAX = 500


def register_batch_routes(bp):
    """Register batch S2T endpoints on the given Blueprint."""

    @bp.route("/api/s2t/batch-transcribe", methods=["POST"])
    async def api_s2t_batch_transcribe():
        """Start batch video transcription in background.

        Input modes (exclusive, specify exactly one):
          - file_ids: [int, ...]  File ID list
          - directory: str        Directory path (recursive option)
          - list_file: str        Text/CSV file path
        Common options:
          - language: str         Language code (default: config value)
          - recursive: bool       Recurse into subdirs for directory mode (default: true)
        """
        data = await request.get_json(silent=True) or {}
        language = data.get("language") or get_default_language()

        # Exclusive input mode check
        has_file_ids = bool(data.get("file_ids"))
        has_directory = bool(data.get("directory"))
        has_list_file = bool(data.get("list_file"))
        mode_count = sum([has_file_ids, has_directory, has_list_file])

        if mode_count == 0:
            return jsonify({
                "status": "error",
                "message": "file_ids, directory, または list_file のいずれかを指定してください",
            }), 400
        if mode_count > 1:
            return jsonify({
                "status": "error",
                "message": "file_ids, directory, list_file は排他的です。1 つだけ指定してください",
            }), 400

        # Resolve file_ids from each input mode
        if has_file_ids:
            file_ids = data["file_ids"]
            if not isinstance(file_ids, list):
                return jsonify({"status": "error", "message": "file_ids はリストで指定してください"}), 400
            file_ids = [fid for fid in file_ids if isinstance(fid, int) and fid > 0]
            if not file_ids:
                return jsonify({"status": "error", "message": "有効な file_id がありません"}), 400
            resolve_info = {"mode": "file_ids"}
        elif has_directory:
            directory = data["directory"]
            recursive = data.get("recursive", True)
            result = resolve_directory(directory, recursive)
            if result["error"]:
                return jsonify({"status": "error", "message": result["error"]}), 400
            file_ids = result["file_ids"]
            resolve_info = {
                "mode": "directory",
                "directory": directory,
                "recursive": recursive,
                "files_found": result["files_found"],
                "matched_in_db": len(file_ids),
            }
        else:
            list_file = data["list_file"]
            result = resolve_list_file(list_file)
            if result["error"]:
                return jsonify({"status": "error", "message": result["error"]}), 400
            file_ids = result["file_ids"]
            resolve_info = {
                "mode": "list_file",
                "list_file": list_file,
                "lines_read": result["lines_read"],
                "matched_in_db": len(file_ids),
            }

        if not file_ids:
            return jsonify({
                "status": "error",
                "message": "対象となる動画/音声ファイルが DB に見つかりませんでした",
            }), 400
        if len(file_ids) > _BATCH_MAX:
            return jsonify({
                "status": "error",
                "message": f"対象ファイル数 {len(file_ids)} が上限 {_BATCH_MAX} を超えています",
            }), 400

        from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
        backend_pref = get_extension_config_value(_EXT_NAME, "backend", "auto")
        model_size = get_extension_config_value(_EXT_NAME, "model_size", "base")
        distributed = data.get("distributed", False)

        t = threading.Thread(
            target=run_batch,
            args=(file_ids, language, backend_pref, model_size, distributed),
            name="s2t-batch",
            daemon=True,
        )
        t.start()
        return jsonify({
            "status": "started",
            "total": len(file_ids),
            **resolve_info,
        })
