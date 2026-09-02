"""Source/raw-metadata helpers for NovelAI v4 extraction."""

import json
from pathlib import Path


def infer_meta_source(filepath: str) -> str:
    from core.helpers_core.helpers_text_path import archive_part
    suf = Path(archive_part(filepath) if "!" in filepath else filepath).suffix.lower()
    if suf == ".png":
        return "novelai_v4_png"
    if suf == ".webp":
        return "novelai_v4_webp"
    return "novelai_v4"


def build_default_raw_meta_json(chunks: dict[str, str]) -> str:
    return json.dumps(
        {
            "Comment": chunks.get("Comment", ""),
            "Description": chunks.get("Description", ""),
            "Software": "NovelAI",
            "Source": chunks.get("Source", ""),
        }
    )
