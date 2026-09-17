"""Speech bubble overlay: render OCR/translation text onto images.

Uses Pillow to draw translated text in detected regions.
Falls back to a text panel appended below the image when bbox is absent.

Drawing utilities are in overlay_drawing.py.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

# Re-export drawing utilities for backward compatibility
from .overlay_drawing import (  # noqa: F401
    _FONT_CANDIDATES_BY_LANG,
    _FONT_CANDIDATES_FALLBACK,
    _LABEL_COLORS,
    _append_text_panel,
    _auto_font_size,
    _draw_text_in_box,
    _find_font,
    _font_cache,
    _get_line_height,
    _load_font,
    _wrap_text,
)
from .types import OcrRegion, OcrResult

logger = logging.getLogger(__name__)


def _maybe_reparse_jsonl_regions(
    regions: list[OcrRegion],
) -> list[OcrRegion]:
    """Compat: re-parse if a single region contains raw JSONL text.

    Fallback for old data where the VLM returned JSONL but the parser
    could not recognize it and stored the raw text as-is.
    """
    import json as _json
    if len(regions) != 1 or not regions[0].text.strip().startswith("{"):
        return regions
    lines = [ln.strip() for ln in regions[0].text.strip().splitlines() if ln.strip()]
    if len(lines) < 2 or not all(ln.startswith("{") for ln in lines):
        return regions
    parsed = []
    for ln in lines:
        try:
            parsed.append(_json.loads(ln))
        except _json.JSONDecodeError:
            return regions  # Parse failure -> return as-is
    # Map for label normalization
    label_map = {
        "speech": "speech_bubble", "speech_bubble": "speech_bubble",
        "thought": "thought_bubble", "thought_bubble": "thought_bubble",
        "sfx": "sfx", "sound_effect": "sfx",
        "narration": "narration", "caption": "caption",
        "title": "title", "sign": "sign",
    }
    new_regions = []
    for i, item in enumerate(parsed):
        text = item.get("text", "")
        if not text or not text.strip():
            continue
        raw_type = item.get("type", "") or item.get("label", "")
        label = label_map.get(raw_type.lower(), "other") if raw_type else "other"
        new_regions.append(OcrRegion(
            region_id=i + 1,
            bbox=item.get("bbox", []),
            text=text.strip(),
            confidence=item.get("confidence", 0.0),
            direction=item.get("direction", "vertical"),
            label=label,
        ))
    return new_regions if new_regions else regions


def generate_overlay(
    image_path: Path,
    ocr: OcrResult,
    translations: dict[int, str] | None = None,
    mode: str = "translated",
    font_size: int = 0,
    bg_opacity: int = 200,
    output_format: str = "PNG",
    translated_full_text: str = "",
    target_lang: str = "",
) -> bytes:
    """Generate an image with OCR text overlaid.

    Regions with bbox are drawn directly inside speech bubbles.
    Regions without bbox are shown as a text panel below the image.
    When regions are empty, full_text / translated_full_text is shown as a panel.

    Args:
        image_path: Source image path
        ocr: OCR result
        translations: region_id -> translated text map (for mode=translated)
        mode: "translated" / "original" / "both"
        font_size: Font size (0 = auto)
        bg_opacity: Background opacity (0-255)
        output_format: Output format (PNG or JPEG)
        translated_full_text: Full-text translation (fallback when no region translations)
        target_lang: Target language code (used for font selection)

    Returns:
        Image binary
    """
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGBA")
    # Select font by target_lang in translation mode, OCR source language in original mode
    font_lang = target_lang if mode in ("translated", "both") and target_lang else ocr.language
    font_path = _find_font(font_lang)

    # Existing data compat: re-parse if JSONL is packed into 1 region
    regions = _maybe_reparse_jsonl_regions(ocr.regions)

    # Classify regions into with/without bbox
    bbox_regions = []
    text_only_regions = []
    for region in regions:
        if region.bbox and len(region.bbox) >= 4 and region.bbox[2] > 0 and region.bbox[3] > 0:
            bbox_regions.append(region)
        else:
            text_only_regions.append(region)

    # -- Regions with bbox: draw directly in speech bubbles --
    if bbox_regions:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for region in bbox_regions:
            text = _resolve_text(region, translations, mode)
            if not text.strip():
                continue
            x, y, w, h = region.bbox
            draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255, bg_opacity))
            fs = font_size if font_size > 0 else _auto_font_size(w, h, text)
            font = _load_font(font_path, fs)
            _draw_text_in_box(draw, text, x, y, w, h, font, region.direction)
        img = Image.alpha_composite(img, overlay)

    # -- Regions without bbox: add text panel below image --
    panel_added = False
    if text_only_regions:
        # Check for per-region translations (matching region_id)
        has_region_trans = translations and any(
            r.region_id in translations for r in text_only_regions
        )
        if has_region_trans or mode == "original":
            panel_lines = _build_panel_lines(text_only_regions, translations, mode)
        else:
            panel_lines = []
        # Fall back to translated_full_text if per-region translation does not match
        if not panel_lines and mode in ("translated", "both") and translated_full_text:
            # Combine re-parsed region text (avoid raw JSON data)
            clean_full = "\n".join(r.text for r in text_only_regions if r.text.strip())
            panel_lines = _build_fulltext_panel(
                clean_full or ocr.full_text, translated_full_text, mode,
            )
        # If still empty, show per-region panels with original text
        if not panel_lines:
            panel_lines = _build_panel_lines(text_only_regions, translations, mode)
        if panel_lines:
            img = _append_text_panel(img, panel_lines, font_path, font_size)
            panel_added = True

    # -- When regions are empty: display full_text as panel --
    if not panel_added and not bbox_regions and not text_only_regions and ocr.full_text:
        panel_lines = _build_fulltext_panel(
            ocr.full_text, translated_full_text, mode,
        )
        if panel_lines:
            img = _append_text_panel(img, panel_lines, font_path, font_size)

    # Output
    buf = io.BytesIO()
    if output_format.upper() == "JPEG":
        img = img.convert("RGB")
        img.save(buf, "JPEG", quality=90)
    else:
        img.save(buf, "PNG")
    return buf.getvalue()


def _resolve_text(
    region: OcrRegion,
    translations: dict[int, str] | None,
    mode: str,
) -> str:
    """Determine display text based on region and mode."""
    if mode == "translated" and translations:
        trans = translations.get(region.region_id, "")
        # Fall back to original text if no translation found
        return trans if trans else region.text
    elif mode == "original":
        return region.text
    elif mode == "both" and translations:
        orig = region.text
        trans = translations.get(region.region_id, "")
        return f"{orig}\n-> {trans}" if trans else orig
    return region.text


def _build_panel_lines(
    regions: list[OcrRegion],
    translations: dict[int, str] | None,
    mode: str,
) -> list[tuple[str, str]]:
    """Build (label, text) list for text panel display."""
    lines = []
    for region in regions:
        text = _resolve_text(region, translations, mode)
        if not text.strip():
            continue
        label = region.label or "text"
        lines.append((label, text))
    return lines


def _build_fulltext_panel(
    full_text: str,
    translated_full_text: str,
    mode: str,
) -> list[tuple[str, str]]:
    """Build panel lines from full_text when regions are empty."""
    lines = []
    if mode == "original":
        if full_text.strip():
            lines.append(("text", full_text))
    elif mode == "translated":
        if translated_full_text.strip():
            lines.append(("text", translated_full_text))
        elif full_text.strip():
            # Fall back to display original text if no translation
            lines.append(("text", full_text))
    elif mode == "both":
        if full_text.strip():
            lines.append(("text", full_text))
        if translated_full_text.strip():
            lines.append(("other", "-> " + translated_full_text))
    return lines
