"""NovelAI-focused WebP metadata extraction."""

import struct
from pathlib import Path


def extract_novelai_webp_metadata(path: Path) -> str | None:
    """Extract NovelAI EXIF UserComment payload from WebP."""
    try:
        with path.open("rb") as f:
            riff = f.read(12)
            if not riff.startswith(b"RIFF") or riff[8:12] != b"WEBP":
                return None

            while True:
                fourcc = f.read(4)
                if len(fourcc) < 4:
                    break
                size_bytes = f.read(4)
                if len(size_bytes) < 4:
                    break
                size = struct.unpack("<I", size_bytes)[0]
                data = f.read(size)
                if size % 2 == 1:
                    f.read(1)

                if fourcc != b"EXIF":
                    continue
                text = _extract_user_comment_from_exif(data)
                if text:
                    return text
        return None
    except Exception:
        return None


def _extract_user_comment_from_exif(data: bytes) -> str | None:
    byte_order = "big" if data[:2] == b"MM" else "little"
    if len(data) < 8:
        return None
    if byte_order == "big":
        ifd_offset = struct.unpack(">I", data[4:8])[0]
        num_entries = struct.unpack(">H", data[ifd_offset:ifd_offset + 2])[0]
    else:
        ifd_offset = struct.unpack("<I", data[4:8])[0]
        num_entries = struct.unpack("<H", data[ifd_offset:ifd_offset + 2])[0]

    for i in range(num_entries):
        entry_offset = ifd_offset + 2 + (i * 12)
        if byte_order == "big":
            tag = struct.unpack(">H", data[entry_offset:entry_offset + 2])[0]
            value_offset = struct.unpack(">I", data[entry_offset + 8:entry_offset + 12])[0]
        else:
            tag = struct.unpack("<H", data[entry_offset:entry_offset + 2])[0]
            value_offset = struct.unpack("<I", data[entry_offset + 8:entry_offset + 12])[0]
        if tag != 0x8769:
            continue
        return _extract_user_comment_from_exif_ifd(data, value_offset, byte_order)
    return None


def _extract_user_comment_from_exif_ifd(data: bytes, value_offset: int, byte_order: str) -> str | None:
    if byte_order == "big":
        exif_num = struct.unpack(">H", data[value_offset:value_offset + 2])[0]
    else:
        exif_num = struct.unpack("<H", data[value_offset:value_offset + 2])[0]

    for j in range(exif_num):
        exif_entry = value_offset + 2 + (j * 12)
        if byte_order == "big":
            exif_tag = struct.unpack(">H", data[exif_entry:exif_entry + 2])[0]
            count = struct.unpack(">I", data[exif_entry + 4:exif_entry + 8])[0]
            val_off = struct.unpack(">I", data[exif_entry + 8:exif_entry + 12])[0]
        else:
            exif_tag = struct.unpack("<H", data[exif_entry:exif_entry + 2])[0]
            count = struct.unpack("<I", data[exif_entry + 4:exif_entry + 8])[0]
            val_off = struct.unpack("<I", data[exif_entry + 8:exif_entry + 12])[0]
        if exif_tag != 0x9286 or val_off + count > len(data):
            continue
        comment_data = data[val_off:val_off + count]
        # Delegate to the shared decoder which auto-detects UTF-16 endianness.
        # NovelAI writes UTF-16-BE; yu_ai_manager bridge writes UTF-16-LE
        # (see core/bridge_core/bridge_save.py::_build_exif_user_comment).
        # The shared decoder uses BOM + content-marker heuristics to pick correctly.
        from core.extractors.exif_decode import decode_exif_user_comment
        decoded = decode_exif_user_comment(comment_data)
        if decoded:
            return decoded
        # Fallback for unknown prefixes
        return comment_data.decode("utf-8", errors="ignore")
    return None
