"""Chunk extraction helpers for regular scanner metadata."""

import json
from pathlib import Path

from core.extractors import (
    extract_novelai_webp_metadata,
    extract_png_text_chunks,
    extract_webm_metadata,
    extract_webp_text_chunks,
)
from core.extractors.exif_chunks import extract_exif_chunks
from core.tagdb_core.media.tagdb_media_flac import extract_flac_chunks


def extract_chunks_for_file(p: Path) -> tuple[dict[str, str], str | None]:
    chunks: dict[str, str] = {}
    nai_raw_meta: str | None = None
    suf = p.suffix.lower()
    if suf == ".png":
        chunks = extract_png_text_chunks(p)
    elif suf == ".webp":
        chunks = extract_webp_text_chunks(p)
        if not chunks or "parameters" not in chunks:
            nai_raw_meta = extract_novelai_webp_metadata(p)
            if nai_raw_meta:
                # yu_ai_manager bridge writes UserComment as
                # "YU_META:" + json.dumps(text_chunks). Strip the marker so
                # the inner JSON (with prompt/workflow keys) is recognized.
                # See core/bridge_core/bridge_save.py::_build_exif_user_comment.
                if nai_raw_meta.startswith("YU_META:"):
                    nai_raw_meta = nai_raw_meta[len("YU_META:"):]
                try:
                    parsed = json.loads(nai_raw_meta)
                    # Valid JSON — populate chunks so extensions can detect format
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            if isinstance(v, str) and k not in chunks:
                                chunks[k] = v
                except (json.JSONDecodeError, TypeError):
                    if "Steps:" in nai_raw_meta or "Sampler:" in nai_raw_meta:
                        chunks["parameters"] = nai_raw_meta
                        chunks["Parameters"] = nai_raw_meta
                    else:
                        chunks["Description"] = nai_raw_meta
                    nai_raw_meta = None
        if not chunks or "parameters" not in chunks:
            exif_chunks = extract_exif_chunks(p)
            if exif_chunks:
                chunks.update(exif_chunks)
    elif suf == ".webm":
        chunks = extract_webm_metadata(p)
    elif suf in (".jpg", ".jpeg", ".jxl", ".avif", ".heif", ".heic"):
        chunks = extract_exif_chunks(p)
    elif suf == ".flac":
        # ComfyUI audio nodes embed prompt/workflow JSON in Vorbis Comments;
        # the comfyui extension's on_scan_file picks it up via chunks.
        chunks = extract_flac_chunks(p)
    elif suf == ".svg":
        # SVG files have no AI generation metadata
        pass
    return chunks, nai_raw_meta
