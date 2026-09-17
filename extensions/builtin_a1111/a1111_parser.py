"""builtin-a1111 extension entrypoint (thin compatibility layer)."""

import sys
from pathlib import Path

_ext_dir = Path(__file__).resolve().parent
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

_project_root = _ext_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from a1111_parser_hooks import on_scan_file_impl
from a1111_sections import on_build_sections_impl as on_build_sections  # noqa: F401
from core.extensions_core.runtime import ExtractedMetadata


def on_scan_file(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    return on_scan_file_impl(filepath, raw_meta, chunks)


def get_blueprint():
    from quart import Blueprint, jsonify

    bp = Blueprint("ext_a1111", __name__)

    @bp.route("/info")
    async def info():
        return jsonify({
            "name": "builtin-a1111",
            "version": "1.1.0",
            "type": "importer",
            "formats": ["a1111_png", "a1111_webp"],
            "description": "Automatic1111 / SD WebUI metadata parser",
        })

    return bp
