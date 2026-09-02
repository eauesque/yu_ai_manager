"""builtin-novelai-v3 extension entrypoint (thin compatibility layer)."""

import sys
from pathlib import Path

_ext_dir = Path(__file__).resolve().parent
if str(_ext_dir) not in sys.path:
    sys.path.insert(0, str(_ext_dir))

_project_root = _ext_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.extensions_core.runtime import ExtractedMetadata
from novelai_v3_hooks import on_scan_file_impl
from novelai_v3_sections import on_build_sections_impl as on_build_sections  # noqa: F401


def on_scan_file(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    return on_scan_file_impl(filepath, raw_meta, chunks)


def get_blueprint():
    from quart import Blueprint, jsonify

    bp = Blueprint("ext_novelai_v3", __name__)

    @bp.route("/info")
    async def info():
        return jsonify({
            "name": "builtin-novelai-v3",
            "version": "1.1.0",
            "type": "importer",
            "formats": ["novelai_v3_png", "novelai_v3_webp"],
            "description": "NovelAI V3 (legacy) metadata parser",
        })

    return bp
