"""WebP text chunk extraction helpers."""

from pathlib import Path

from core.extractors.webp_chunks_handlers import handle_exif_chunk, handle_unknown_chunk, handle_xmp_chunk
from core.extractors.webp_chunks_parse import parse_webp_chunks


def extract_webp_text_chunks(path: Path) -> dict[str, str]:
    """Extract EXIF/XMP/custom text chunks from a WebP file."""
    out: dict[str, str] = {}
    try:
        all_chunks = parse_webp_chunks(path)
        for fourcc, data in all_chunks:
            if fourcc == b"EXIF":
                handle_exif_chunk(data, out)
            elif fourcc == b"XMP ":
                handle_xmp_chunk(data, out)
            elif fourcc not in (b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"):
                handle_unknown_chunk(fourcc, data, out)
        return out
    except Exception:
        return out
