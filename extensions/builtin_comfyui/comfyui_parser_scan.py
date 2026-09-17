"""ComfyUI scan hook implementation."""


from core.extensions_core.runtime import ExtractedMetadata

from core.extract_core.comfyui_extract_helpers import extract_comfyui_json, find_clip_texts, infer_comfy_meta_source


def on_scan_file_impl(filepath: str, raw_meta: str | None, chunks: dict[str, str]) -> ExtractedMetadata | None:
    """on_scan_file hook -- detect and extract ComfyUI JSON."""
    if not chunks:
        return None

    raw_json, obj = extract_comfyui_json(chunks)
    if not raw_json:
        return None

    meta_source = infer_comfy_meta_source(filepath)
    raw_prompt = None
    raw_negative = None
    tag_source = None
    pos_texts: list[str] = []
    neg_texts: list[str] = []

    if obj is not None:
        pos_texts, neg_texts = find_clip_texts(obj)
        if pos_texts:
            raw_prompt = pos_texts[0]
            tag_source = pos_texts[0]
        if neg_texts:
            raw_negative = neg_texts[0]

    return ExtractedMetadata(
        meta_source=meta_source,
        format="comfy",
        raw_prompt=raw_prompt,
        raw_negative=raw_negative,
        raw_meta_json=raw_json,
        tag_source=tag_source,
        extra={
            "has_workflow": "workflow" in chunks,
            "has_prompt_chunk": "prompt" in chunks,
            "positive_count": len(pos_texts),
            "negative_count": len(neg_texts),
        },
    )
