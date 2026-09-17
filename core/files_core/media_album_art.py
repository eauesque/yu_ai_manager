"""Extract embedded album art from audio files.

Uses tinytag (MIT) to extract cover art from MP3, FLAC, OGG, M4A etc.
Returns raw image bytes or None.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import BinaryIO


def extract_album_art(source: str | Path | io.BytesIO | bytes | BinaryIO) -> bytes | None:
    """Return embedded cover-art bytes, or *None* if unavailable.

    Parameters
    ----------
    source:
        A file path (str / Path) or in-memory audio data (BytesIO / bytes).
    """
    try:
        return _extract(source)
    except Exception:
        return None


def _extract(source: str | Path | io.BytesIO | bytes | BinaryIO) -> bytes | None:
    from tinytag import TinyTag

    if isinstance(source, (str, Path)):
        tag = TinyTag.get(str(source), image=True)
    elif isinstance(source, bytes):
        bio = io.BytesIO(source)
        tag = TinyTag.get(file_obj=bio, image=True)
    elif hasattr(source, "read"):
        with contextlib.suppress(Exception):
            source.seek(0)
        tag = TinyTag.get(file_obj=source, image=True)
    else:
        return None

    if tag is None:
        return None

    image_data = tag.get_image()
    if image_data:
        return image_data
    return None
