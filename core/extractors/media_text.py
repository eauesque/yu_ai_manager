"""Shared text normalization and result packing for media extractor."""

import json
from typing import Any


def norm_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s.replace("\x00", "").strip()


def first_value(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        for x in v:
            sx = norm_text(x)
            if sx:
                return sx
        return ""
    return norm_text(v)


def pack_result(meta: dict[str, Any], kind: str) -> dict[str, Any]:
    title = norm_text(meta.get("title"))
    artist = norm_text(meta.get("artist"))
    album = norm_text(meta.get("album"))
    genre = norm_text(meta.get("genre"))
    comment = norm_text(meta.get("comment"))

    prompt_parts = [x for x in [title, artist, album, genre] if x]
    tag_parts = [x for x in [title, artist, album, genre, comment] if x]
    prompt = ", ".join(prompt_parts) if prompt_parts else None
    tag_source = ", ".join(tag_parts) if tag_parts else None

    return {
        "success": True,
        "meta_source": f"media_{kind}",
        "format": "media",
        "raw_prompt": prompt,
        "raw_negative": None,
        "raw_meta_json": json.dumps(meta, ensure_ascii=False),
        "tag_source": tag_source,
    }
