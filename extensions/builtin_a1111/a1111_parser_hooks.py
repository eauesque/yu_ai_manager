"""Hook handlers for A1111 extension."""


from a1111_parser_parse import (
    detect_meta_source,
    extract_parameters_text,
    parse_a1111,
)
from core.extensions_core.runtime import ExtractedMetadata


def on_scan_file_impl(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    """Extract metadata for scan pipeline from A1111 parameters."""
    if not chunks:
        return None

    params_text = extract_parameters_text(chunks)
    if not params_text:
        return None

    if "Steps:" not in params_text and "Sampler:" not in params_text:
        return None

    positive, negative, params = parse_a1111(params_text)
    meta_source = detect_meta_source(filepath, chunks)

    return ExtractedMetadata(
        meta_source=meta_source,
        format="sd",
        raw_prompt=params_text,
        raw_negative=negative or None,
        raw_meta_json=None,
        tag_source=positive,
        extra={"params": params},
    )
