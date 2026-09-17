"""
Metadata Extractor for AI Image Generation.

Supports:
- NovelAI V3/V4 (PNG, WebP)
- Stable Diffusion (A1111, Forge)
- ComfyUI
- Tensor.art
"""

import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

from .formats import (
    extract_comfyui,
    extract_novelai,
    extract_sd,
    extract_stealth,
)
from .formats_audio import extract_flac_vorbis
from .models import extract_model_info

_AUDIO_VORBIS_EXTS = frozenset({".flac"})


def extract_metadata(image_path: Path) -> tuple[str | None, str | None, str, str | None]:
    """Extract metadata from an image or audio file.

    For FLAC, parse Vorbis Comments and reuse the existing ComfyUI/A1111
    dispatchers — ComfyUI audio nodes (e.g. MMAudio) embed `prompt` and
    `workflow` in the same shape PIL exposes for PNG.
    """
    suffix = image_path.suffix.lower()

    if suffix in _AUDIO_VORBIS_EXTS:
        try:
            comments = extract_flac_vorbis(image_path)
        except Exception as e:
            logger.debug("Vorbis comment read failed for %s: %s", image_path, e)
            comments = None
        if comments:
            if "parameters" in comments:
                return extract_sd({"parameters": comments["parameters"]})
            if "prompt" in comments or "workflow" in comments:
                info: dict[str, Any] = {}
                if "prompt" in comments:
                    info["prompt"] = comments["prompt"]
                if "workflow" in comments:
                    info["workflow"] = comments["workflow"]
                return extract_comfyui(info)
        return (None, None, "unknown", None)

    try:
        with Image.open(image_path) as img:
            info = img.info

            if "Title" in info or "Description" in info or "Comment" in info:
                return extract_novelai(info, suffix)

            if "parameters" in info:
                return extract_sd(info)

            if "prompt" in info or "workflow" in info:
                return extract_comfyui(info)

        stealth = extract_stealth(image_path)
        if stealth[0] or stealth[1]:
            return stealth

        return (None, None, "unknown", None)

    except Exception as e:
        logger.error(f"Error extracting metadata from {image_path}: {e}")
        return (None, None, "unknown", None)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 1:
        print("Usage: python metadata_extractor.py <image_path>")
        return 1

    image_path = Path(args[0])

    if not image_path.exists():
        print(f"Error: File not found: {image_path}")
        return 1

    print(f"Extracting metadata from: {image_path}")
    print("=" * 60)

    positive, negative, fmt, raw_meta = extract_metadata(image_path)

    print(f"\nFormat: {fmt}")
    print("\nPositive Prompt:")
    print(positive or "(none)")
    print("\nNegative Prompt:")
    print(negative or "(none)")

    if raw_meta:
        print("\nRaw Metadata (truncated):")
        print(raw_meta[:500] + "..." if len(raw_meta) > 500 else raw_meta)

    model_name, model_hash = extract_model_info(raw_meta)
    if model_name:
        print(f"\nModel: {model_name}")
        if model_hash:
            print(f"Hash: {model_hash}")
    return 0


__all__ = ["extract_metadata", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
