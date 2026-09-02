"""Post text assembly + X Intent URL generation."""

import unicodedata
import urllib.parse
from typing import Any


def count_graphemes(text: str) -> int:
    """Approximate Unicode grapheme count (for Bluesky 300 grapheme limit).

    Accurate grapheme cluster splitting requires a third-party library,
    but a simple implementation excluding combining characters suffices here.
    """
    return sum(1 for ch in text if unicodedata.category(ch) not in ("Mn", "Mc", "Me"))


def _truncate_graphemes(text: str, limit: int) -> str:
    """Truncate by grapheme count and append "..."."""
    count = 0
    cut_idx = len(text)
    for i, ch in enumerate(text):
        if unicodedata.category(ch) in ("Mn", "Mc", "Me"):
            continue
        count += 1
        if count > limit:
            cut_idx = i
            break
    if cut_idx < len(text):
        return text[:cut_idx].rstrip() + "..."
    return text


def _get_file_meta(file_id: int) -> dict[str, Any]:
    """Get metadata from DB for post template expansion.

    files テーブルにはプロンプトがなく、templates テーブルに格納されている。
    """
    from core.services_core.db_api import get_readonly_db
    con = get_readonly_db()
    row = con.execute(
        "SELECT f.path, t.raw_prompt, t.raw_negative, t.raw_meta_json "
        "FROM files f LEFT JOIN templates t ON t.file_id = f.id "
        "WHERE f.id=? AND f.is_deleted=0",
        (file_id,),
    ).fetchone()
    if not row:
        return {}

    import json
    path = row[0] or ""
    positive = row[1] or ""
    negative = row[2] or ""
    params_raw = row[3] or "{}"

    try:
        params = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
    except (json.JSONDecodeError, TypeError):
        params = {}
    if not isinstance(params, dict):
        params = {}

    # Top 5 tags (from file_tags, ordered by overall usage frequency)
    tag_rows = con.execute(
        "SELECT t.tag FROM file_tags ft JOIN tags t ON ft.tag_id=t.id "
        "WHERE ft.file_id=? "
        "ORDER BY (SELECT COUNT(*) FROM file_tags ft2 WHERE ft2.tag_id=t.id) DESC "
        "LIMIT 5",
        (file_id,),
    ).fetchall()
    top_tags = ", ".join(r[0] for r in tag_rows) if tag_rows else ""

    import os
    filename = os.path.basename(path)

    return {
        "positive": positive,
        "positive_short": positive[:100] + ("..." if len(positive) > 100 else ""),
        "negative_short": negative[:50] + ("..." if len(negative) > 50 else ""),
        "model": params.get("model", params.get("Model", "")),
        "seed": str(params.get("seed", params.get("Seed", ""))),
        "steps": str(params.get("steps", params.get("Steps", ""))),
        "cfg": str(params.get("cfg_scale", params.get("CFG scale", ""))),
        "sampler": params.get("sampler", params.get("Sampler", "")),
        "size": params.get("size", params.get("Size", "")),
        "tags": top_tags,
        "filename": filename,
    }


def build_post_text(
    file_id: int,
    template: str | None = None,
) -> dict[str, Any]:
    """Expand template and return post text and meta info."""
    meta = _get_file_meta(file_id)
    if not meta:
        return {"error": "file_not_found", "text": "", "graphemes": 0}

    if template is None:
        from .credential_store import load_sns_config
        sns = load_sns_config()
        template = sns.get("post_template", "{positive_short}")

    text = template
    for key, val in meta.items():
        text = text.replace("{" + key + "}", str(val))

    graphemes = count_graphemes(text)

    return {
        "text": text,
        "graphemes": graphemes,
        "meta": meta,
    }


def build_x_intent_url(file_id: int, text: str | None = None) -> str:
    """Generate an X (Twitter) Web Intent URL."""
    if text is None:
        result = build_post_text(file_id)
        text = result.get("text", "")

    # X allows 280 chars with URL, but trim to ~200 for safety
    text = _truncate_graphemes(text, 200)

    params = urllib.parse.urlencode({"text": text})
    return f"https://x.com/intent/tweet?{params}"
