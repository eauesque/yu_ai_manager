"""Text position detection (bbox) -- OCR second pass.

Queries VLM for position information on regions with extracted text.
Attaches confidence scores since VLM-returned coordinates may be inaccurate.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

from .types import OcrRegion

logger = logging.getLogger(__name__)

# bbox detection prompt
# Ask VLM for text positions. Coordinates are returned as ratios (0.0-1.0) of image size.
# Ratios tend to give better VLM accuracy than pixel coordinates.
_BBOX_PROMPT = (
    "I found these texts in the image. "
    "For each numbered text, provide its bounding box as [left, top, right, bottom] "
    "where values are ratios (0.0 to 1.0) of image width/height.\n"
    "Reply with JSON array ONLY:\n"
    '[{"id": 1, "bbox": [left, top, right, bottom]}]\n\n'
)


def detect_bboxes(
    image_path: Path,
    regions: list[OcrRegion],
    analysis_engine,
    image_width: int = 0,
    image_height: int = 0,
) -> list[OcrRegion]:
    """Detect bbox for each region using VLM.

    Args:
        image_path: 画像ファイルパス
        regions: テキスト抽出済みの region リスト
        analysis_engine: VLM AnalysisEngine
        image_width: 画像幅 (0 なら自動取得)
        image_height: 画像高さ (0 なら自動取得)

    Returns:
        bbox が付与された region リスト (検出できなかった region は元のまま)
    """
    if not regions:
        return regions

    # Only target regions with text
    valid = [(i, r) for i, r in enumerate(regions) if r.text.strip()]
    if not valid:
        return regions

    # Get image size
    if not image_width or not image_height:
        image_width, image_height = _get_image_size(image_path)
        if not image_width or not image_height:
            logger.warning("Cannot determine image size for bbox detection")
            return regions

    # Build prompt: numbered text list
    # Sanitize text content to prevent prompt injection
    lines = []
    for idx, (_, region) in enumerate(valid):
        text_preview = region.text[:50].replace("\n", " ")
        # Remove control characters and strings commonly used in prompt injection
        text_preview = text_preview.replace("[", "(").replace("]", ")")
        lines.append(f"{idx + 1}. \"{text_preview}\"")

    prompt = _BBOX_PROMPT + "\n".join(lines)

    # Query VLM
    try:
        result = analysis_engine.analyze_image(
            image_path, existing_tags=[], existing_prompt=prompt, mode="ocr",
        )
        raw = result.raw_response or ""
    except Exception as exc:
        logger.warning("bbox detection VLM call failed: %s", exc)
        return regions

    # Parse response
    bbox_map = _parse_bbox_response(raw, image_width, image_height)
    if not bbox_map:
        logger.info("bbox detection: no valid bboxes found in VLM response")
        return regions

    # Apply bbox to regions
    updated = list(regions)
    for idx, (orig_idx, region) in enumerate(valid):
        bbox_id = idx + 1
        if bbox_id in bbox_map:
            bbox = bbox_map[bbox_id]
            updated[orig_idx] = OcrRegion(
                region_id=region.region_id,
                bbox=bbox,
                text=region.text,
                confidence=region.confidence,
                direction=region.direction,
                label=region.label,
            )

    detected = sum(1 for _, (oi, _) in enumerate(valid) if updated[oi].bbox)
    logger.info("bbox detection: %d/%d regions located", detected, len(valid))
    return updated


def _parse_bbox_response(
    raw: str,
    img_w: int,
    img_h: int,
) -> dict[int, list[int]]:
    """Extract bbox from VLM response.

    Returns:
        Map of {id: [x, y, w, h]} (pixel coordinates)
    """
    # JSON extraction
    data = _extract_json_list(raw)
    if not data:
        return {}

    result = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        bid = item.get("id")
        bbox_raw = item.get("bbox", [])
        if bid is None or not isinstance(bbox_raw, list) or len(bbox_raw) < 4:
            continue

        try:
            values = [float(v) for v in bbox_raw[:4]]
        except (ValueError, TypeError):
            continue

        # NaN / Inf check
        if any(math.isnan(v) or math.isinf(v) for v in values):
            continue

        # Determine if ratio or pixel coordinates
        if all(0.0 <= v <= 1.0 for v in values):
            # Ratio -> pixel conversion [left, top, right, bottom] -> [x, y, w, h]
            left, top, right, bottom = values
            x = int(left * img_w)
            y = int(top * img_h)
            w = int((right - left) * img_w)
            h = int((bottom - top) * img_h)
        elif all(v >= 0 for v in values):
            # Assume pixel coordinates
            if len(values) == 4:
                v0, v1, v2, v3 = [int(v) for v in values]
                # [left, top, right, bottom] → [x, y, w, h]
                if v2 > v0 and v3 > v1:
                    x, y, w, h = v0, v1, v2 - v0, v3 - v1
                # [x, y, w, h] as-is
                elif v2 > 0 and v3 > 0 and v2 < img_w and v3 < img_h:
                    x, y, w, h = v0, v1, v2, v3
                else:
                    continue
            else:
                continue
        else:
            continue

        # Sanity check
        if w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= img_w + 5 and y + h <= img_h + 5:
            result[bid] = [
                max(0, x), max(0, y),
                min(w, img_w - x), min(h, img_h - y),
            ]

    return result


def _extract_json_list(raw: str) -> list:
    """Extract JSON array from response."""
    # ```json ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(1))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    # Direct
    stripped = raw.strip()
    try:
        result = json.loads(stripped)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Look for [ ... ]
    m = re.search(r"\[.*\]", stripped, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return []


def _get_image_size(image_path: Path) -> tuple[int, int]:
    """Get image dimensions."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return 0, 0
