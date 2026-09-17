"""YU_META UserComment unwrap helper.

yu_ai_manager bridge save embeds generation metadata as
``"YU_META:" + json.dumps(text_chunks)`` inside the EXIF UserComment of
WebP/JPEG/etc. files (see :mod:`core.bridge_core.bridge_save`). Without
this unwrap step, downstream chunk handlers see the JSON-encoded value's
inner ``"Steps:"`` / ``"Negative prompt:"`` substrings and mistakenly
treat the entire ``YU_META:{...}`` blob as a raw A1111 parameters string,
breaking later prompt parsing (positive ends up containing the literal
JSON wrapper plus escaped ``\\n`` separators).
"""

from __future__ import annotations

import json

YU_META_PREFIX = "YU_META:"


def unwrap_yu_meta(text: str | None) -> dict[str, str] | None:
    """Return the inner chunks dict if *text* is a YU_META JSON envelope.

    Returns ``None`` when the prefix is absent or the JSON payload is
    malformed / not a dict, so callers can fall back to legacy parsing.
    Only string values are surfaced; nested objects / arrays are dropped
    because the chunk handlers downstream expect ``dict[str, str]``.
    """
    if not text or not text.startswith(YU_META_PREFIX):
        return None
    try:
        parsed = json.loads(text[len(YU_META_PREFIX):])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {k: v for k, v in parsed.items() if isinstance(v, str)}
