"""FLAC Vorbis Comment helper for the regular-scan metadata pipeline.

Thin wrapper around `core.tools.metadata.formats_audio.extract_flac_vorbis`
that returns a chunks dict shaped like PNG tEXt / WebP EXIF chunks so the
existing ComfyUI / A1111 chunk-extractors can be reused.
"""

from __future__ import annotations

from pathlib import Path

from core.tools.metadata.formats_audio import extract_flac_vorbis


def extract_flac_chunks(p: Path) -> dict[str, str]:
    """Read FLAC Vorbis comments and return them as a string-string dict.

    Returns {} if the file is not FLAC, has no comments, or fails to parse.
    Keys are lower-cased per Vorbis convention; ComfyUI emits 'prompt' and
    'workflow' which line up with PIL's PNG info dict.
    """
    comments = extract_flac_vorbis(p)
    if not comments:
        return {}
    return {k: v for k, v in comments.items() if isinstance(v, str)}


__all__ = ["extract_flac_chunks"]
