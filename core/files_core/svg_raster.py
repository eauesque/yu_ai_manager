"""SVG rasterization helpers using resvg (Rust-based, cross-platform).

Provides PNG output from SVG files or raw SVG byte strings.
Falls back gracefully when resvg is not installed.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SVG_AVAILABLE = False
_usvg = None
_render = None

try:
    from resvg._resvg import render as _render  # resvg 0.2 package layout
    from resvg._resvg import usvg as _usvg

    SVG_AVAILABLE = True
except (ImportError, AttributeError):
    # Try legacy single-module layout (resvg < 0.2)
    try:
        import resvg as _resvg_mod

        _usvg = _resvg_mod.usvg
        _render = _resvg_mod.render
        SVG_AVAILABLE = True
    except (ImportError, AttributeError):
        pass


def is_svg_file(path_str: str) -> bool:
    """Return True if the file has an .svg extension."""
    return Path(path_str).suffix.lower() == ".svg"


def _build_tree(svg_data: bytes):
    """Parse SVG bytes into a resvg Tree object.

    resvg 0.2 merged FontDatabase into Options — fonts are loaded directly on
    the Options instance and Tree.from_str takes (svg_str, options).
    """
    opts = _usvg.Options.default()
    opts.load_system_fonts()
    return _usvg.Tree.from_str(svg_data.decode("utf-8"), opts)


def rasterize_svg(
    svg_path: Path,
    width: int = 0,
    height: int = 0,
    *,
    background: str = "",
) -> bytes:
    """Rasterize an SVG file to PNG bytes.

    If *width* / *height* are 0 the intrinsic SVG size is used.
    Returns raw PNG data.
    """
    if not SVG_AVAILABLE:
        raise RuntimeError("resvg is not installed (pip install resvg)")

    svg_data = svg_path.read_bytes()
    return rasterize_svg_bytes(svg_data, width, height, background=background)


def rasterize_svg_bytes(
    svg_data: bytes,
    width: int = 0,
    height: int = 0,
    *,
    background: str = "",
) -> bytes:
    """Rasterize raw SVG bytes to PNG bytes.

    If *width* / *height* are 0 the intrinsic SVG size is used.
    A scaling transform is applied when a target size is specified.
    """
    if not SVG_AVAILABLE:
        raise RuntimeError("resvg is not installed (pip install resvg)")

    tree = _build_tree(svg_data)
    iw, ih = tree.int_size()

    # Compute scale transform
    if width > 0 and height > 0 and iw > 0 and ih > 0:
        sx = width / iw
        sy = height / ih
        # Uniform scale (fit inside target)
        scale = min(sx, sy)
        transform = (scale, 0.0, 0.0, scale, 0.0, 0.0)
    else:
        transform = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    # render() returns a list of bytes (PNG data)
    png_list = _render(tree, transform)
    png_data = bytes(png_list)

    # If background colour requested, composite onto it
    if background and png_data:
        png_data = _apply_background(png_data, background)

    return png_data


def _apply_background(png_data: bytes, bg_colour: str) -> bytes:
    """Composite the RGBA PNG onto a solid background colour."""
    try:
        from PIL import Image

        fg = Image.open(io.BytesIO(png_data)).convert("RGBA")
        bg = Image.new("RGBA", fg.size, bg_colour)
        bg.paste(fg, mask=fg)
        buf = io.BytesIO()
        bg.convert("RGB").save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        # If Pillow colour parse fails, return as-is
        return png_data


def get_svg_dimensions(svg_path: Path) -> tuple[int | None, int | None]:
    """Extract width/height from an SVG file using resvg or XML fallback.

    Returns (width, height) or (None, None) if parsing fails.
    """
    if SVG_AVAILABLE:
        try:
            tree = _build_tree(svg_path.read_bytes())
            w, h = tree.int_size()
            if w > 0 and h > 0:
                return w, h
        except Exception:
            logger.debug("file metadata step failed", exc_info=True)

    # Fallback: parse viewBox / width / height from XML
    return _parse_svg_dimensions_xml(svg_path)


def _parse_svg_dimensions_xml(svg_path: Path) -> tuple[int | None, int | None]:
    """Parse SVG root element for width/height/viewBox using stdlib XML."""
    import re

    import defusedxml.ElementTree as ET

    try:
        et = ET.parse(svg_path)
        root = et.getroot()

        # Strip namespace prefix
        def _attr(name: str) -> str | None:
            return root.get(name)

        w_str = _attr("width")
        h_str = _attr("height")

        def _to_int(s: str | None) -> int | None:
            if not s:
                return None
            m = re.match(r"(\d+(?:\.\d+)?)", s)
            return int(float(m.group(1))) if m else None

        w, h = _to_int(w_str), _to_int(h_str)
        if w and h:
            return w, h

        # Try viewBox
        vb = _attr("viewBox")
        if vb:
            parts = re.split(r"[\s,]+", vb.strip())
            if len(parts) >= 4:
                try:
                    return int(float(parts[2])), int(float(parts[3]))
                except (ValueError, IndexError):
                    pass
    except Exception:
        logger.debug("file metadata step failed", exc_info=True)

    return None, None
