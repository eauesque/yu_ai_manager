"""Fallback metadata extraction helpers for regular scanner."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.extractors import extract_media_metadata


def apply_chunk_fallback(p: Path, chunks: dict[str, str], meta_source: str, fmt: str):
    raw_prompt: str | None = None
    raw_negative: str | None = None
    raw_meta_json: str | None = None
    tag_source: str | None = None

    if "prompt" in chunks and "nai_json" in chunks:
        raw_prompt = chunks.get("prompt", "")
        raw_negative = chunks.get("negative", "")
        raw_meta_json = chunks.get("nai_json")
        meta_source = "nai_webp"
        fmt = "nai"
        tag_source = raw_prompt
    elif "Comment" in chunks and p.suffix.lower() == ".webp":
        comment = chunks["Comment"]
        if '"v4_prompt"' in comment or '"prompt"' in comment:
            raw_prompt = chunks.get("Description", "")
            raw_meta_json = comment
            meta_source = "nai_webp"
            fmt = "nai"
            tag_source = raw_prompt
    elif ("parameters" in chunks or "Parameters" in chunks):
        params_text = chunks.get("parameters") or chunks.get("Parameters", "")
        if params_text and ("Steps:" in params_text or "Sampler:" in params_text):
            raw_prompt = params_text
            suf = p.suffix.lower()
            meta_source = f"a1111_{suf.lstrip('.')}" if suf else "a1111_png"
            fmt = "sd"
            from core.prompt import parse_a1111_prompt

            parsed_a = parse_a1111_prompt(params_text)
            raw_negative = parsed_a.get("negative", "")
            tag_source = parsed_a.get("positive", raw_prompt)
    elif "Description" in chunks and p.suffix.lower() == ".webp":
        desc = chunks["Description"]
        if len(desc) > 20:
            raw_prompt = desc
            meta_source = "webp_desc"
            fmt = "unknown"
            tag_source = desc

    return raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source


def apply_bytes_metadata_fallback(
    p: Path,
    raw_prompt: str | None,
    raw_negative: str | None,
    raw_meta_json: str | None,
    meta_source: str,
    fmt: str,
    tag_source: str | None,
) -> tuple[str | None, str | None, str | None, str, str, str | None]:
    if raw_prompt is None and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".jxl", ".avif", ".heif", ".heic", ".webp"):
        try:
            suf = p.suffix.lower()
            if suf == ".png":
                from core.extractors.png_bytes import extract_png_metadata

                meta_result = extract_png_metadata(p)
            elif suf == ".webp":
                from core.extractors.webp_bytes import extract_webp_metadata

                meta_result = extract_webp_metadata(p)
            else:
                from core.extractors.exif_jpeg import extract_jpeg_metadata

                meta_result = extract_jpeg_metadata(p)

            if meta_result.get("success"):
                meta_source = meta_result.get("meta_source", meta_source)
                fmt = meta_result.get("format", fmt)
                raw_prompt = meta_result.get("raw_prompt")
                raw_negative = meta_result.get("raw_negative")
                raw_meta_json = meta_result.get("raw_meta_json")
                tag_source = raw_prompt
        except Exception as e:
            logger.warning(f"metadata extraction fallback failed for {p}: {e}")
    return raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source


def apply_media_metadata_fallback(
    p: Path,
    raw_prompt: str | None,
    raw_negative: str | None,
    raw_meta_json: str | None,
    meta_source: str,
    fmt: str,
    tag_source: str | None,
) -> tuple[str | None, str | None, str | None, str, str, str | None]:
    if raw_prompt is None and p.suffix.lower() in (
        ".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac",
        ".webm", ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".ogv",
    ):
        try:
            media_meta = extract_media_metadata(p)
            if media_meta.get("success"):
                meta_source = media_meta.get("meta_source", meta_source)
                fmt = media_meta.get("format", fmt)
                raw_prompt = media_meta.get("raw_prompt")
                raw_negative = media_meta.get("raw_negative")
                raw_meta_json = media_meta.get("raw_meta_json")
                tag_source = media_meta.get("tag_source") or raw_prompt
            elif media_meta.get("raw_meta_json") is not None:
                meta_source = media_meta.get("meta_source", "media_error")
                fmt = media_meta.get("format", "media")
                raw_meta_json = media_meta.get("raw_meta_json")
                raw_prompt = None
                raw_negative = None
                tag_source = None
        except Exception as e:
            logger.warning(f"media metadata extraction failed for {p}: {e}")
    return raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source
