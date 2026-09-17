"""TinyTag-backed media metadata extraction.

Replaces mutagen (GPL-2.0+) with tinytag (MIT).
"""

import io
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import contextlib

from core.extractors.media_text import norm_text, pack_result


def _extract_from_tinytag(tag: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if tag is None:
        return meta

    for field, attr in [
        ("title", "title"),
        ("artist", "artist"),
        ("album", "album"),
        ("genre", "genre"),
        ("date", "year"),
        ("tracknumber", "track"),
        ("comment", "comment"),
    ]:
        val = getattr(tag, attr, None)
        if val is not None:
            s = norm_text(val)
            if s:
                meta[field] = s

    duration = getattr(tag, "duration", None)
    if duration is not None:
        with contextlib.suppress(ValueError, TypeError):
            meta["duration_sec"] = round(float(duration), 3)

    return meta


def extract_with_mutagen(filething: Any) -> dict[str, Any]:
    """Extract media metadata using tinytag.

    Function name kept for backward compatibility with callers.
    """
    try:
        from tinytag import TinyTag
    except Exception:
        return {"success": False}

    try:
        if isinstance(filething, (str, Path)):
            tag = TinyTag.get(str(filething), image=False)
        elif isinstance(filething, io.BytesIO):
            filething.seek(0)
            tag = TinyTag.get(file_obj=filething, image=False)
        else:
            return {"success": False}
    except Exception:
        return {"success": False}

    if tag is None:
        return {"success": False}

    # Determine kind from file extension or defaults to audio
    kind = "audio"
    if isinstance(filething, (str, Path)):
        ext = Path(str(filething)).suffix.lower()
        if ext in (".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov", ".ogv"):
            kind = "video"

    meta = _extract_from_tinytag(tag)
    if not meta:
        return {"success": False}
    return pack_result(meta, kind)
