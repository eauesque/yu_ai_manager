"""Hook handlers for NovelAI v3 (legacy) extension."""

from core.extensions_core.runtime import ExtractedMetadata
from novelai_v3_parse import try_png_old_format, try_webp_nai_json, try_webp_old_format


def on_scan_file_impl(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    """Extract legacy NovelAI metadata for scan pipeline."""
    if not chunks:
        return None

    comment = chunks.get("Comment", "")
    software = chunks.get("Software", "")
    if software == "NovelAI" and comment:
        parsed = try_png_old_format(comment, chunks.get("Description", ""))
        if parsed:
            return ExtractedMetadata(
                meta_source=parsed["meta_source"],
                format=parsed["format"],
                raw_prompt=parsed["raw_prompt"],
                raw_negative=parsed["raw_negative"],
                raw_meta_json=parsed["raw_meta_json"],
                tag_source=parsed["tag_source"],
            )

    if raw_meta:
        parsed = try_webp_old_format(raw_meta)
        if parsed:
            return ExtractedMetadata(
                meta_source=parsed["meta_source"],
                format=parsed["format"],
                raw_prompt=parsed["raw_prompt"],
                raw_negative=parsed["raw_negative"],
                raw_meta_json=parsed["raw_meta_json"],
                tag_source=parsed["tag_source"],
            )

    nai_json = chunks.get("nai_json")
    if nai_json:
        parsed = try_webp_nai_json(nai_json, chunks.get("prompt", ""), chunks.get("negative", ""))
        if parsed:
            return ExtractedMetadata(
                meta_source=parsed["meta_source"],
                format=parsed["format"],
                raw_prompt=parsed["raw_prompt"],
                raw_negative=parsed["raw_negative"],
                raw_meta_json=parsed["raw_meta_json"],
                tag_source=parsed["tag_source"],
            )

    return None
