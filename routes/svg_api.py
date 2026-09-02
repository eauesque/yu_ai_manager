"""SVG rasterization API endpoints."""

import base64
import logging
import os
from pathlib import Path

from quart import Blueprint, request

from core.files_core.svg_raster import SVG_AVAILABLE, rasterize_svg, rasterize_svg_bytes
from core.infra_core.api_params import clamp_sqlite_int
from core.services_core.db_api import get_readonly_db
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

logger = logging.getLogger(__name__)

bp = Blueprint("svg_api", __name__)


def _allowed_svg_path_bases() -> list[Path]:
    """Return roots allowed for direct svg_path rasterization."""
    bases: list[Path] = []
    try:
        from core.paths import get_cache_dir, get_data_dir, get_profiles_dir

        bases.extend([get_data_dir(), get_cache_dir(), get_profiles_dir()])
    except Exception:
        cwd = Path.cwd()
        bases.extend([cwd / "data", cwd / "cache", cwd / "profiles"])
    return bases


def _is_under_base(path: Path, base: Path) -> bool:
    real_path = os.path.realpath(path)
    real_base = os.path.realpath(base)
    try:
        return os.path.commonpath([real_path, real_base]) == real_base
    except ValueError:
        return False


def _resolve_allowed_svg_path(path_value: str) -> Path | None:
    p = Path(path_value).expanduser()
    if p.suffix.lower() != ".svg":
        return None
    if not p.exists():
        return None
    return p if any(_is_under_base(p, base) for base in _allowed_svg_path_bases()) else None


@bp.route("/api/svg/rasterize", methods=["POST"])
async def svg_rasterize():
    """Rasterize an SVG to PNG/WebP bitmap.

    Request JSON:
        file_id (int): File ID from database (SVG file)
        svg_path (str): Filesystem path to SVG file
        svg_data (str): Raw SVG string (inline)
        width (int): Target width (default 1024)
        height (int): Target height (default 1024)
        format (str): Output format "png" or "webp" (default "png")
        background (str): Background colour hex (default transparent)

    One of file_id, svg_path, or svg_data must be provided.
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    if not SVG_AVAILABLE:
        return {"ok": False, "error": "resvg is not installed (pip install resvg)"}, 501

    data = await request.get_json(force=True, silent=True) or {}
    try:
        file_id = clamp_sqlite_int(int(data.get("file_id", 0)))
    except (TypeError, ValueError):
        file_id = 0
    svg_path = data.get("svg_path", "")
    svg_data_str = data.get("svg_data", "")
    width = int(data.get("width", 1024))
    height = int(data.get("height", 1024))
    out_format = data.get("format", "png").lower()
    background = data.get("background", "")

    if out_format not in ("png", "webp"):
        return {"ok": False, "error": "format must be 'png' or 'webp'"}, 400

    try:
        if file_id:
            png_data = _rasterize_from_db(file_id, width, height, background)
        elif svg_path:
            p = Path(svg_path)
            if p.suffix.lower() != ".svg":
                return {"ok": False, "error": "Not an SVG file"}, 400
            if not p.exists():
                return {"ok": False, "error": "SVG file not found"}, 404
            p = _resolve_allowed_svg_path(svg_path)
            if p is None:
                return {"ok": False, "error": "svg_path is outside allowed directories"}, 400
            png_data = rasterize_svg(p, width, height, background=background)
        elif svg_data_str:
            svg_bytes = svg_data_str.encode("utf-8") if isinstance(svg_data_str, str) else svg_data_str
            png_data = rasterize_svg_bytes(svg_bytes, width, height, background=background)
        else:
            return {"ok": False, "error": "Provide file_id, svg_path, or svg_data"}, 400

        # Convert to WebP if requested
        if out_format == "webp" and png_data:
            png_data = _png_to_webp(png_data)

        b64 = base64.b64encode(png_data).decode("ascii")

        # Get actual dimensions from the output
        actual_w, actual_h = _get_png_dimensions(png_data)

        return {
            "ok": True,
            "base64": b64,
            "width": actual_w or width,
            "height": actual_h or height,
            "format": out_format,
            "size_bytes": len(png_data),
        }

    except Exception:
        logger.exception("SVG rasterization failed")
        return {"ok": False, "error": "SVG rasterization failed"}, 500


@bp.route("/api/svg/info", methods=["GET"])
async def svg_info():
    """Check SVG rasterization availability."""
    return {
        "available": SVG_AVAILABLE,
        "backend": "resvg" if SVG_AVAILABLE else None,
    }


def _rasterize_from_db(file_id: int, width: int, height: int, background: str) -> bytes:
    """Look up file_id in DB and rasterize."""
    from pathlib import Path

    con = get_readonly_db()
    row = con.execute("SELECT path FROM files WHERE id=? AND is_deleted=0", (file_id,)).fetchone()
    if not row:
        raise ValueError(f"File ID {file_id} not found")

    p = Path(row[0])
    if p.suffix.lower() != ".svg":
        raise ValueError(f"File ID {file_id} is not an SVG file")
    if not p.exists():
        raise FileNotFoundError(f"SVG file not found: {p}")

    return rasterize_svg(p, width, height, background=background)


def _png_to_webp(png_data: bytes) -> bytes:
    """Convert PNG bytes to WebP bytes."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png_data))
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=90)
    return buf.getvalue()


def _get_png_dimensions(data: bytes):
    """Quick extraction of PNG/WebP dimensions."""
    try:
        import io

        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return img.width, img.height
    except Exception:
        return None, None
