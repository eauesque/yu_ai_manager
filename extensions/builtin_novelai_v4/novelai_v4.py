"""builtin-novelai-v4 Extension -- NovelAI V4 metadata extraction."""

import sys
from pathlib import Path

_ext_dir = Path(__file__).resolve().parent
_project_root = _ext_dir.parent.parent
for _p in (str(_ext_dir), str(_project_root)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.extensions_core.runtime import ExtractedMetadata  # noqa: E402
from novelai_v4_sections import on_build_sections_impl as on_build_sections  # noqa: E402, F401

from core.extract_core.novelai_v4_extract_helpers import (  # noqa: E402
    build_scan_metadata,
    parse_v4_data,
)


def on_scan_file(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    """on_scan_file hook -- detect and extract NovelAI V4 format."""
    if not chunks:
        return None

    comment = chunks.get("Comment", "")
    software = chunks.get("Software", "")
    data, raw_override = parse_v4_data(comment, software, raw_meta)
    if not data:
        return None

    return build_scan_metadata(filepath, data, chunks, raw_meta_json=raw_override)


def get_blueprint():
    from quart import Blueprint, jsonify

    bp = Blueprint("ext_novelai_v4", __name__)

    @bp.route("/info")
    async def info():
        return jsonify({
            "name": "builtin-novelai-v4",
            "version": "1.1.0",
            "type": "importer",
            "formats": ["novelai_v4_png", "novelai_v4_webp"],
            "description": "NovelAI V4 metadata parser (Character Prompts, Vibe Transfer)",
        })

    return bp
