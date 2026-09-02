"""NovelAI v4 metadata builders."""


from core.extensions_core.lifecycle.runtime import (
    DetailSection,
    ExtractedMetadata,
)

from .novelai_v4_extract_prompts import extract_base_and_char_prompts
from .novelai_v4_extract_source import build_default_raw_meta_json, infer_meta_source


def build_scan_metadata(filepath: str, data: dict, chunks: dict[str, str], raw_meta_json: str | None = None) -> ExtractedMetadata:
    positive_parts, _ = extract_base_and_char_prompts(data, "v4_prompt", "prompt")
    negative_parts, _ = extract_base_and_char_prompts(data, "v4_negative_prompt", "uc")

    return ExtractedMetadata(
        meta_source=infer_meta_source(filepath),
        format="novelai_v4",
        raw_prompt=", ".join(positive_parts),
        raw_negative=", ".join(negative_parts),
        raw_meta_json=raw_meta_json or build_default_raw_meta_json(chunks),
        tag_source=", ".join(positive_parts),
        extra={
            "has_v4_prompt": "v4_prompt" in data,
            "has_v4_negative": "v4_negative_prompt" in data,
            "char_count": len(data.get("v4_prompt", {}).get("caption", {}).get("char_captions", [])),
        },
    )


def build_sections(filepath: str, data: dict, chunks: dict[str, str], raw_meta_json: str | None = None) -> list[DetailSection]:
    """Build DetailSection list for on_build_sections hook (replaces old build_inspect_result)."""
    _, char_positives = extract_base_and_char_prompts(data, "v4_prompt", "prompt")
    _, char_negatives = extract_base_and_char_prompts(data, "v4_negative_prompt", "uc")

    sections: list[DetailSection] = []
    if char_positives:
        sections.append(
            DetailSection(
                title="V4 Characters (Positive)",
                display_type="list",
                content=char_positives,
                copyable=True,
            )
        )
    if char_negatives:
        sections.append(
            DetailSection(
                title="V4 Characters (Negative)",
                display_type="list",
                content=char_negatives,
                copyable=True,
            )
        )

    if data.get("reference_image_multiple"):
        sections.append(
            DetailSection(
                title="Reference Images",
                display_type="table",
                content=[
                    {"index": i, "strength": r.get("information_extracted", "?")}
                    for i, r in enumerate(data["reference_image_multiple"])
                ],
            )
        )

    return sections
