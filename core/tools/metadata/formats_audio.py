"""Audio container metadata extraction (FLAC Vorbis Comments).

Reads the Vorbis Comment block from a FLAC file and returns an info dict
that is shape-compatible with `PIL.Image.info` so the existing
`extract_comfyui` / `extract_sd` paths can be reused.

Spec references:
- FLAC stream layout: 'fLaC' magic + sequence of metadata blocks.
  Block header = 1 byte (last_flag<<7 | type) + 3 bytes BE length.
  type 4 = VORBIS_COMMENT.
- Vorbis Comment payload (little-endian):
  uint32 vendor_length, vendor (utf-8),
  uint32 comment_count,
  for each comment: uint32 length, 'KEY=value' (utf-8).

Per Vorbis spec the same key may repeat; we keep the last occurrence
(ComfyUI does not currently emit duplicates).
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

logger = logging.getLogger(__name__)

# Hard cap on a single Vorbis Comment block to avoid pathological files.
# ComfyUI workflows are typically well under 64 KiB.
_MAX_BLOCK_BYTES = 4 * 1024 * 1024


def extract_flac_vorbis(path: Path) -> dict[str, str] | None:
    """Return Vorbis comments as a {key: value} dict, or None on failure.

    Keys are lower-cased to match Vorbis comment case-insensitivity rules.
    Returns None if the file is not FLAC or has no Vorbis Comment block.
    """
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"fLaC":
                return None

            for _ in range(64):  # FLAC has at most a small handful of blocks
                hdr = f.read(4)
                if len(hdr) < 4:
                    return None
                b0 = hdr[0]
                last = bool(b0 & 0x80)
                btype = b0 & 0x7F
                blen = int.from_bytes(hdr[1:4], "big")
                if blen > _MAX_BLOCK_BYTES:
                    logger.warning("FLAC block too large (%d bytes) in %s", blen, path)
                    return None

                if btype == 4:  # VORBIS_COMMENT
                    body = f.read(blen)
                    if len(body) < blen:
                        return None
                    return _parse_vorbis_comment(body)

                # Skip non-comment blocks
                f.seek(blen, 1)
                if last:
                    return None
    except OSError as e:
        logger.debug("FLAC read failed for %s: %s", path, e)
        return None

    return None


def _parse_vorbis_comment(body: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    off = 0
    if len(body) < 4:
        return out
    (vlen,) = struct.unpack_from("<I", body, off)
    off += 4
    off += vlen  # skip vendor string

    if off + 4 > len(body):
        return out
    (n,) = struct.unpack_from("<I", body, off)
    off += 4

    for _ in range(n):
        if off + 4 > len(body):
            break
        (clen,) = struct.unpack_from("<I", body, off)
        off += 4
        if off + clen > len(body):
            break
        try:
            comment = body[off : off + clen].decode("utf-8", "replace")
        except Exception:
            off += clen
            continue
        off += clen
        key, sep, val = comment.partition("=")
        if not sep:
            continue
        out[key.lower()] = val
    return out


__all__ = ["extract_flac_vorbis"]
