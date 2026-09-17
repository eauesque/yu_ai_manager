"""Result builders for NovelAI v3 legacy parser."""

import json
from typing import Any


def build_png_result(comment: str, description: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta_source": "novelai_png",
        "format": "novelai",
        "raw_prompt": data.get("prompt", ""),
        "raw_negative": data.get("uc", ""),
        "raw_meta_json": json.dumps({"Comment": comment, "Description": description}),
        "tag_source": data.get("prompt", ""),
        "data": data,
        "source_type": "png",
    }


def build_webp_result(raw_meta: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta_source": "novelai_webp",
        "format": "novelai",
        "raw_prompt": data.get("prompt", ""),
        "raw_negative": data.get("uc", ""),
        "raw_meta_json": raw_meta,
        "tag_source": data.get("prompt", ""),
        "data": data,
        "source_type": "webp",
    }


def build_nai_chunk_result(nai_json: str, prompt: str, negative: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta_source": "nai_webp",
        "format": "nai",
        "raw_prompt": prompt,
        "raw_negative": negative,
        "raw_meta_json": nai_json,
        "tag_source": prompt,
        "data": payload,
        "source_type": "webp",
    }
