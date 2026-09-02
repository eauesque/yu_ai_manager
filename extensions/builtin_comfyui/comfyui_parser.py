"""builtin-comfyui Extension — ComfyUI parser hooks facade."""

import sys
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_project_root = _this_dir.parent.parent.parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from comfyui_parser_scan import on_scan_file_impl  # noqa: E402
from comfyui_sections import on_build_sections_impl as on_build_sections  # noqa: E402, F401
from core.extensions_core.runtime import ExtractedMetadata  # noqa: E402


def on_scan_file(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    return on_scan_file_impl(filepath, raw_meta, chunks)


def get_blueprint():
    from quart import Blueprint, jsonify

    bp = Blueprint("ext_comfyui", __name__)

    @bp.route("/info")
    async def info():
        return jsonify({
            "name": "builtin-comfyui",
            "version": "1.1.0",
            "type": "importer",
            "formats": ["comfy_png", "comfy_webm"],
            "description": "ComfyUI workflow JSON metadata parser",
        })

    return bp
