"""Overlay drawing utilities — font loading, text rendering, and panel generation.

Separated from overlay.py for maintainability.
"""

from __future__ import annotations

import contextlib
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

# Per-language font candidates -- select appropriate font based on target language
_FONT_CANDIDATES_BY_LANG: dict[str, list[str]] = {
    "zh": [
        # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
        # Windows -- Microsoft YaHei covers simplified/traditional Chinese and Japanese widely
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ],
    "ko": [
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ],
    "ja": [
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/YuGothR.ttc",
        "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4\u30b7\u30c3\u30af W3.ttc",
    ],
}

# Generic CJK + Latin fallback (common to all languages)
_FONT_CANDIDATES_FALLBACK = [
    # Pan-CJK (Linux)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    # Windows -- YaHei is excellent as a general CJK fallback
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    # macOS
    "/System/Library/Fonts/\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4\u30b7\u30c3\u30af W3.ttc",
    "/System/Library/Fonts/AppleGothic.ttf",
    # Latin fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
]

_font_cache: dict[str, str] = {}


def _find_font(lang: str = "") -> str | None:
    """Return font path for given language. Results are cached."""
    cache_key = lang or "_default"
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    # Search in order: language-specific candidates -> generic fallback
    candidates = list(_FONT_CANDIDATES_BY_LANG.get(lang, []))
    # Also handle regional codes like zh-TW, zh-CN
    if not candidates and "-" in lang:
        base = lang.split("-")[0]
        candidates = list(_FONT_CANDIDATES_BY_LANG.get(base, []))
    candidates.extend(_FONT_CANDIDATES_FALLBACK)

    for fp in candidates:
        if Path(fp).exists():
            _font_cache[cache_key] = fp
            return fp
    _font_cache[cache_key] = ""
    return ""


def _auto_font_size(w: int, h: int, text: str) -> int:
    """Estimate font size from bbox dimensions and text length."""
    char_count = max(len(text.replace("\n", "")), 1)
    # Estimate per-character size based on area
    area = w * h
    size_per_char = math.sqrt(area / char_count)
    fs = max(8, min(int(size_per_char * 0.8), 72))
    return fs


def _load_font(font_path: str | None, size: int):
    """Load font. Falls back to default font (may not support CJK)."""
    from PIL import ImageFont
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as exc:
            logger.warning("Font load failed (%s, size=%d): %s", font_path, size, exc)
    logger.info("Using default font (CJK characters may not render correctly)")
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    from PIL import Image, ImageDraw

    # Temporary draw object (for textbbox)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    result_lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            result_lines.append("")
            continue
        words = list(paragraph)  # Character-level (CJK support)
        line = ""
        for ch in words:
            test = line + ch
            bbox = tmp.textbbox((0, 0), test, font=font)
            tw = bbox[2] - bbox[0]
            if tw > max_width and line:
                result_lines.append(line)
                line = ch
            else:
                line = test
        if line:
            result_lines.append(line)
    return result_lines or [""]


def _get_line_height(font) -> int:
    """Get line height for given font."""
    from PIL import Image, ImageDraw
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = tmp.textbbox((0, 0), "Agj\u56fd", font=font)
    return int((bbox[3] - bbox[1]) * 1.3)


def _draw_text_in_box(
    draw, text: str, x: int, y: int, w: int, h: int,
    font, direction: str = "horizontal",
) -> None:
    """Draw text within a bounding box. Shrinks font if overflowing."""
    from PIL import ImageFont

    padding = 4
    inner_w = w - padding * 2
    inner_h = h - padding * 2
    if inner_w <= 0 or inner_h <= 0:
        return

    # Text wrapping
    lines = _wrap_text(text, font, inner_w)
    line_height = _get_line_height(font)
    total_height = line_height * len(lines)

    # Shrink font size and recalculate if overflowing
    if total_height > inner_h and hasattr(font, 'path'):
        ratio = inner_h / total_height
        new_size = max(8, int(font.size * ratio))
        with contextlib.suppress(Exception):
            font = ImageFont.truetype(font.path, new_size)
        lines = _wrap_text(text, font, inner_w)
        line_height = _get_line_height(font)
        total_height = line_height * len(lines)

    # Drawing start position (vertically centered)
    start_y = y + padding + max(0, (inner_h - total_height) // 2)

    for i, line in enumerate(lines):
        ly = start_y + i * line_height
        if ly + line_height > y + h:
            break
        # Horizontally centered
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        lx = x + padding + max(0, (inner_w - tw) // 2)
        # Outline (improved readability)
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            draw.text((lx + dx, ly + dy), line, fill=(0, 0, 0, 180), font=font)
        draw.text((lx, ly), line, fill=(255, 255, 255, 255), font=font)


# Background color per label (R, G, B)
_LABEL_COLORS = {
    "speech_bubble": (59, 130, 246),
    "thought_bubble": (99, 155, 255),
    "sfx": (245, 158, 11),
    "narration": (139, 92, 246),
    "caption": (168, 85, 247),
    "title": (236, 72, 153),
    "sign": (16, 185, 129),
    "other": (107, 114, 128),
}


def _append_text_panel(
    img: Image.Image,
    lines: list[tuple[str, str]],
    font_path: str | None,
    font_size: int = 0,
) -> Image.Image:
    """Append a text panel below the image."""
    from PIL import Image, ImageDraw

    img_w = img.width
    padding = 12
    line_gap = 6
    fs = font_size if font_size > 0 else max(14, min(img_w // 40, 24))
    font = _load_font(font_path, fs)
    font_small = _load_font(font_path, max(10, fs - 4))

    # Calculate panel height
    total_height = padding
    line_data = []
    for label, text in lines:
        # Label row
        label_h = _get_line_height(font_small)
        # Text rows
        wrapped = _wrap_text(text, font, img_w - padding * 2 - 16)
        text_h = _get_line_height(font) * len(wrapped)
        entry_h = label_h + text_h + line_gap
        line_data.append((label, wrapped, label_h, entry_h))
        total_height += entry_h
    total_height += padding

    # Create panel image
    panel = Image.new("RGBA", (img_w, total_height), (24, 24, 32, 240))
    draw = ImageDraw.Draw(panel)

    y = padding
    for label, wrapped, label_h, _entry_h in line_data:
        # Label badge
        color = _LABEL_COLORS.get(label, _LABEL_COLORS["other"])
        badge_w = draw.textlength(label.upper(), font=font_small) + 12
        draw.rounded_rectangle(
            [padding, y, padding + badge_w, y + label_h],
            radius=4,
            fill=(*color, 180),
        )
        draw.text(
            (padding + 6, y + 1), label.upper(),
            fill=(255, 255, 255, 255), font=font_small,
        )
        y += label_h + 2

        # Text
        for wl in wrapped:
            draw.text((padding + 8, y), wl, fill=(255, 255, 255, 240), font=font)
            y += _get_line_height(font)
        y += line_gap

    # Combine original image with panel
    combined = Image.new("RGBA", (img_w, img.height + total_height), (0, 0, 0, 0))
    combined.paste(img, (0, 0))
    combined.paste(panel, (0, img.height))
    return combined
