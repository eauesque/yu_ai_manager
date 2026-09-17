"""Shared constants and preprocessing helpers for inference engines."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
INPUT_SIZE = 448
DEFAULT_GENERAL_THRESHOLD = 0.35
DEFAULT_CHARACTER_THRESHOLD = 0.85

CATEGORY_MAP: dict[int, str] = {
    0: "general",
    4: "character",
    3: "copyright",
    9: "rating",
}


# ---------------------------------------------------------------------------
# Tag CSV parsing
# ---------------------------------------------------------------------------
def parse_tags_csv(csv_path: Path, logger) -> tuple[list[str], list[str]]:
    """Parse selected_tags.csv and return (tag_names, categories)."""
    tag_names: list[str] = []
    categories: list[str] = []
    with open(csv_path, encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                continue
            category = CATEGORY_MAP.get(int(row.get("category", "0")), "general")
            tag_names.append(name)
            categories.append(category)
    logger.info("Parsed %d tags from %s", len(tag_names), csv_path.name)
    return tag_names, categories


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------
def preprocess_image_bytes(
    image_data: bytes, size: int = INPUT_SIZE
) -> np.ndarray:
    """Preprocess image bytes for WD-Tagger inference.

    Returns an array of shape (1, size, size, 3) with dtype float32.
    Alpha channel is composited onto a white background and the image
    is resized with aspect-preserving padding.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image_data)).convert("RGBA")
    canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
    canvas.alpha_composite(img)
    img = canvas.convert("RGB")

    old_w, old_h = img.size
    scale = size / max(old_w, old_h)
    new_w = int(old_w * scale)
    new_h = int(old_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    padded = Image.new("RGB", (size, size), (255, 255, 255))
    padded.paste(img, ((size - new_w) // 2, (size - new_h) // 2))

    # BGR channel order expected by WD-Tagger models
    arr = np.array(padded, dtype=np.float32)[:, :, ::-1]
    return np.expand_dims(arr, axis=0)


# ---------------------------------------------------------------------------
# Tag list building
# ---------------------------------------------------------------------------
def build_tag_list(
    probs,
    tag_names: list[str],
    categories: list[str],
    general_threshold: float = DEFAULT_GENERAL_THRESHOLD,
    character_threshold: float = DEFAULT_CHARACTER_THRESHOLD,
) -> list[dict]:
    """Build filtered tag list from probability vector."""
    tags = []
    for i, (name, category) in enumerate(zip(tag_names, categories, strict=False)):
        if i >= len(probs):
            break
        conf = float(probs[i])
        if category == "rating":
            continue
        threshold = (
            character_threshold if category == "character" else general_threshold
        )
        if conf >= threshold:
            tags.append(
                {"tag": name, "confidence": round(conf, 4), "category": category}
            )
    tags.sort(key=lambda tag: tag["confidence"], reverse=True)
    return tags


# ---------------------------------------------------------------------------
# Multipart extraction
# ---------------------------------------------------------------------------
def _extract_boundary(content_type: str) -> bytes | None:
    """Extract the boundary token from a Content-Type header."""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            return part[9:].strip().encode()
    return None


def _extract_part_payload(part: bytes) -> bytes | None:
    """Extract the payload from a single multipart part."""
    header_end = part.find(b"\r\n\r\n")
    if header_end < 0:
        return None
    payload = part[header_end + 4 :]
    if payload.endswith(b"\r\n"):
        payload = payload[:-2]
    if payload.endswith(b"--"):
        payload = payload[:-2]
    if payload.endswith(b"\r\n"):
        payload = payload[:-2]
    return payload or None


def extract_multipart_image(
    body: bytes, content_type: str
) -> bytes | None:
    """Extract the 'image' field from multipart/form-data body."""
    boundary = _extract_boundary(content_type)
    if boundary is None:
        return None
    for part in body.split(b"--" + boundary):
        if b'name="image"' in part:
            return _extract_part_payload(part)
    return None


def extract_multipart_images(
    body: bytes, content_type: str
) -> list[bytes]:
    """Extract all 'images' fields from multipart/form-data body."""
    boundary = _extract_boundary(content_type)
    if boundary is None:
        return []
    results = []
    for part in body.split(b"--" + boundary):
        if b'name="images"' in part:
            payload = _extract_part_payload(part)
            if payload:
                results.append(payload)
    return results
