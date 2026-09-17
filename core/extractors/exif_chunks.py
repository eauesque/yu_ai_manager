"""Chunk-format wrappers around EXIF UserComment extraction."""

from pathlib import Path

from core.extractors.exif_comment_decode import (
    extract_exif_user_comment,
    extract_exif_user_comment_from_bytes,
)
from core.extractors.yu_meta import unwrap_yu_meta


def _chunks_from_user_comment(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    # YU_META JSON envelope must be unwrapped before the Steps/Sampler
    # heuristic, otherwise the JSON value's inner substrings cause the
    # whole "YU_META:{...}" wrapper to be returned as parameters text.
    inner = unwrap_yu_meta(text)
    if inner is not None:
        return dict(inner)
    if "Steps:" in text or "Sampler:" in text:
        return {"parameters": text, "Parameters": text}
    return {}


def extract_exif_chunks(path: Path) -> dict[str, str]:
    return _chunks_from_user_comment(extract_exif_user_comment(path))


def extract_exif_chunks_from_bytes(data: bytes) -> dict[str, str]:
    return _chunks_from_user_comment(extract_exif_user_comment_from_bytes(data))
