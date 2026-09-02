"""Extension-based metadata extraction dispatch for ZIP entries."""

import os
import struct
from pathlib import Path
from typing import Any

from core.extractors import (
    extract_jpeg_metadata,
    extract_jpeg_metadata_from_bytes,
    extract_media_metadata,
    extract_media_metadata_from_bytes,
    extract_png_metadata,
    extract_png_metadata_from_bytes,
    extract_webp_metadata,
    extract_webp_metadata_from_bytes,
)

_MEDIA_EXTS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".opus",
    ".m4a",
    ".aac",
    ".flac",
    ".webm",
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".ogv",
}


def _extract_webp_exif_a1111(result: dict[str, Any], source: bytes | str | Path) -> None:
    from core.extractors.exif_user_comment import _parse_exif_user_comment
    from core.extractors.webp_chunks_parse import parse_webp_chunks
    from core.prompt import parse_a1111_prompt

    if isinstance(source, bytes):
        file_bytes = source
        if file_bytes[:4] != b"RIFF" or file_bytes[8:12] != b"WEBP":
            return
        pos = 12
        chunks: list[tuple[bytes, bytes]] = []
        while pos + 8 <= len(file_bytes):
            fourcc = file_bytes[pos : pos + 4]
            ln = struct.unpack("<I", file_bytes[pos + 4 : pos + 8])[0]
            chunk_data = file_bytes[pos + 8 : pos + 8 + ln]
            chunks.append((fourcc, chunk_data))
            pos += 8 + ln + (ln % 2)
    else:
        chunks = parse_webp_chunks(Path(source))

    for fourcc, chunk_data in chunks:
        if fourcc == b"EXIF":
            uc = _parse_exif_user_comment(chunk_data)
            if uc and ("Steps:" in uc or "Sampler:" in uc):
                parsed = parse_a1111_prompt(uc)
                result["raw_prompt"] = uc
                result["raw_negative"] = parsed.get("negative", "")
                result["meta_source"] = "a1111_webp"
                result["format"] = "sd"
                result["success"] = True
                result["tag_source"] = parsed.get("positive", uc)
            return


def is_media_metadata_extension(internal_path: str) -> bool:
    return os.path.splitext(internal_path)[1].lower() in _MEDIA_EXTS


def apply_extractor_by_extension(result: dict[str, Any], internal_path: str, source: bytes | str | Path) -> None:
    ext = os.path.splitext(internal_path)[1].lower()

    if ext == ".png":
        if isinstance(source, bytes):
            result.update(extract_png_metadata_from_bytes(source))
        else:
            result.update(extract_png_metadata(Path(source)))
    elif ext == ".webp":
        if isinstance(source, bytes):
            result.update(extract_webp_metadata_from_bytes(source))
        else:
            result.update(extract_webp_metadata(Path(source)))
        if not result.get("success"):
            _extract_webp_exif_a1111(result, source)
    elif ext in (".jpg", ".jpeg"):
        if isinstance(source, bytes):
            result.update(extract_jpeg_metadata_from_bytes(source))
        else:
            result.update(extract_jpeg_metadata(Path(source)))
    elif ext in (".jxl", ".avif", ".heif", ".heic"):
        from core.extractors.exif_comment_decode import (
            extract_exif_user_comment,
            extract_exif_user_comment_from_bytes,
        )

        if isinstance(source, bytes):
            text = extract_exif_user_comment_from_bytes(source)
        else:
            text = extract_exif_user_comment(Path(source))
        if text and ("Steps:" in text or "Sampler:" in text):
            result["raw_prompt"] = text
            result["meta_source"] = f"a1111_{ext.lstrip('.')}"
            result["format"] = "sd"
            result["success"] = True
    elif ext in _MEDIA_EXTS:
        if isinstance(source, bytes):
            result.update(extract_media_metadata_from_bytes(source))
        else:
            result.update(extract_media_metadata(Path(source)))
