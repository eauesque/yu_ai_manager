"""Metadata extraction phase for regular-file scanner."""

from pathlib import Path

from core.extractors.sidecar import read_sidecar_txt

from .scanner_regular_meta import (
    apply_bytes_metadata_fallback,
    apply_chunk_fallback,
    apply_media_metadata_fallback,
    extract_chunks_for_file,
)
from .scanner_state import try_extension_parsers


def extract_regular_metadata(p: Path) -> tuple[str, str, str | None, str | None, str | None, str | None]:
    meta_source = "unknown"
    raw_prompt: str | None = None
    raw_negative: str | None = None
    raw_meta_json: str | None = None
    fmt = "unknown"
    tag_source: str | None = None

    side = read_sidecar_txt(p)
    if side:
        raw_prompt = side
        meta_source = "txt"

    chunks: dict[str, str] = {}
    nai_raw_meta: str | None = None
    if raw_prompt is None:
        chunks, nai_raw_meta = extract_chunks_for_file(p)

    if raw_prompt is None:
        ext_result = try_extension_parsers(str(p), nai_raw_meta, chunks)
        if ext_result is not None:
            meta_source = ext_result.meta_source or meta_source
            fmt = ext_result.format or fmt
            raw_prompt = ext_result.raw_prompt
            raw_negative = ext_result.raw_negative
            raw_meta_json = ext_result.raw_meta_json
            tag_source = ext_result.tag_source

    if raw_prompt is None and chunks:
        raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source = apply_chunk_fallback(
            p, chunks, meta_source, fmt
        )

    raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source = apply_bytes_metadata_fallback(
        p, raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source
    )
    raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source = apply_media_metadata_fallback(
        p, raw_prompt, raw_negative, raw_meta_json, meta_source, fmt, tag_source
    )

    return meta_source, fmt, raw_prompt, raw_negative, raw_meta_json, tag_source
