"""VLM OCR response parsers — Markdown, text format handling, and quality checks.

JSON extraction utilities are in vlm_ocr_json.py.
"""

from __future__ import annotations

import re

from .types import OcrRegion, OcrResult

# Re-export JSON utilities for backward compatibility
from .vlm_ocr_json import (  # noqa: F401
    extract_json_any,
    extract_json_object,
    fallback_text,
    regions_from_json_array,
    regions_from_json_object,
)
from .vlm_ocr_prompts import normalize_label

# ── Manga OCR parser (all formats supported) ──


def parse_manga_any_format(raw: str) -> list[OcrRegion]:
    """Convert VLM output to region list regardless of format."""
    parsed = extract_json_any(raw)

    # 1. JSON array: [{"text":"...", "type":"..."}]
    if isinstance(parsed, list):
        regions = regions_from_json_array(parsed)
        if regions:
            return regions

    # 2. JSON object: {"regions": [...]}
    if isinstance(parsed, dict):
        regions = regions_from_json_object(parsed)
        if regions:
            return regions

    # 3. Markdown / text format
    regions = parse_manga_from_text(raw)
    if regions:
        return regions

    # 4. Final fallback: return entire raw text as 1 region
    text = fallback_text(raw)
    if text:
        return [OcrRegion(
            region_id=1, text=text, label="other", direction="vertical",
        )]
    return []


def parse_manga_from_text(raw: str) -> list[OcrRegion]:
    """Extract regions from Markdown/text format response.

    Fallback for when VLM returns Markdown lists or quotes instead of JSON.
    Recognized patterns:
    - **Speech bubble**: "text"  or  **SFX**: text
    - [speech] text  or  [sfx] text
    - - text (list item)
    - *"text"* (italic quote)
    - 1. text (numbered list)
    """
    regions: list[OcrRegion] = []
    rid = 1

    # Label estimation keywords
    _sfx_hints = {"sound effect", "sfx", "onomatopoeia", "\u52b9\u679c\u97f3", "se"}
    _narration_hints = {"narration", "caption", "\u30ca\u30ec\u30fc\u30b7\u30e7\u30f3", "\u30ad\u30e3\u30d7\u30b7\u30e7\u30f3"}
    _title_hints = {"title", "heading", "chapter", "\u30bf\u30a4\u30c8\u30eb", "\u7ae0"}
    _sign_hints = {"sign", "label", "\u770b\u677f", "\u8868\u793a"}

    # Pattern 1: **label**: text or **label** text
    for m in re.finditer(
        r'\*\*([^*]+)\*\*\s*:?\s*[\u300c"\']*([^\u300c\u300d"\'\n*]+)[\u300d"\']*',
        raw,
    ):
        label_hint = m.group(1).strip().lower()
        text = m.group(2).strip()
        if not text or len(text) < 1:
            continue
        label = normalize_label(label_hint)
        regions.append(OcrRegion(
            region_id=rid, text=text, label=label, direction="vertical",
        ))
        rid += 1

    # Pattern 2: [label] text
    if not regions:
        for m in re.finditer(r'\[([^\]]+)\]\s*(.+)', raw):
            label_hint = m.group(1).strip()
            text = m.group(2).strip()
            # Remove markdown decoration
            text = re.sub(r'[*_`]', '', text).strip()
            text = re.sub(r'^[\u300c"\']|[\u300d"\']$', '', text).strip()
            if not text or len(text) < 1:
                continue
            label = normalize_label(label_hint)
            regions.append(OcrRegion(
                region_id=rid, text=text, label=label, direction="vertical",
            ))
            rid += 1

    # Pattern 3: italic quote *"text"* or *"text"*
    if not regions:
        for m in re.finditer(r'\*[\u300c"\'](.*?)[\u300d"\']\*', raw):
            text = m.group(1).strip()
            if not text:
                continue
            context_start = max(0, m.start() - 80)
            context = raw[context_start:m.start()].lower()
            label = _guess_label_from_context(
                context, text, _sfx_hints, _narration_hints,
                _title_hints, _sign_hints,
            )
            regions.append(OcrRegion(
                region_id=rid, text=text, label=label, direction="vertical",
            ))
            rid += 1

    # Pattern 4: list items (- text or * text or 1. text)
    if not regions:
        for m in re.finditer(r'(?:^|\n)\s*(?:[-\u2022*]|\d+\.)\s+(.+)', raw):
            text = m.group(1).strip()
            # Remove markdown decoration
            text = re.sub(r'\*+', '', text)
            text = re.sub(r'[\u300c\u300d\u201c\u201d\u2018\u2019\'\']', '', text)
            text = text.strip()
            if not text or len(text) < 2:
                continue
            # Skip English description text
            if re.match(r'^[A-Za-z\s()\[\]:]{20,}$', text):
                continue
            context = raw[max(0, m.start() - 80):m.start()].lower()
            label = _guess_label_from_context(
                context, text, _sfx_hints, _narration_hints,
                _title_hints, _sign_hints,
            )
            regions.append(OcrRegion(
                region_id=rid, text=text, label=label, direction="vertical",
            ))
            rid += 1

    return regions


def _guess_label_from_context(
    context: str, text: str,
    sfx_hints: set, narration_hints: set,
    title_hints: set, sign_hints: set,
) -> str:
    """Guess label from surrounding context and text content."""
    for hint in sfx_hints:
        if hint in context:
            return "sfx"
    for hint in narration_hints:
        if hint in context:
            return "narration"
    for hint in title_hints:
        if hint in context:
            return "title"
    for hint in sign_hints:
        if hint in context:
            return "sign"
    # Short katakana-only text may be SFX (mixed hiragana = dialogue)
    if len(text) <= 4 and re.match(r'^[\u30A0-\u30FF\u30FC]+$', text):
        return "sfx"
    return "speech_bubble"


def deduplicate_regions(regions: list[OcrRegion]) -> list[OcrRegion]:
    """Remove duplicate text regions."""
    seen_texts: set = set()
    unique: list[OcrRegion] = []
    rid = 1
    for r in regions:
        normalized = r.text.strip()
        if not normalized or normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        unique.append(OcrRegion(
            region_id=rid,
            bbox=r.bbox,
            text=r.text,
            confidence=r.confidence,
            direction=r.direction,
            label=r.label,
        ))
        rid += 1
    return unique


def manga_parse_quality(ocr: OcrResult) -> int:
    """Return parse quality score for manga OCR result (higher is better).

    - More regions = VLM recognized text individually
    - Non-"other" labels = type classification succeeded
    - bbox present = position info available
    - Text without JSON syntax = clean parse
    """
    if not ocr.regions:
        return 0
    score = 0
    for r in ocr.regions:
        score += 10  # Regions exist
        if r.label and r.label != "other":
            score += 3  # Has label classification
        if r.bbox and len(r.bbox) >= 4:
            score += 5  # Has position info
        if not r.text.strip().startswith("{"):
            score += 2  # Not JSON syntax
    return score


def should_retry_manga(ocr: OcrResult) -> bool:
    """Determine if manga OCR result is low quality and should be retried."""
    if not ocr.regions:
        return True
    # All text in 1 region (parse failure)
    if len(ocr.regions) == 1 and ocr.regions[0].label == "other":
        return True
    # All regions are raw JSON text
    return bool(all(r.text.strip().startswith("{") for r in ocr.regions))
