"""Raw TIFF/EXIF parser for UserComment extraction."""

import struct

from core.extractors.exif_decode import decode_exif_user_comment


def extract_user_comment_raw(data: bytes) -> str | None:
    tiff_data = find_tiff_in_container(data)
    if not tiff_data:
        return None
    return parse_tiff_user_comment(tiff_data)


def find_tiff_in_container(data: bytes) -> bytes | None:
    idx = data.find(b"Exif")
    while idx >= 4:
        box_size = struct.unpack(">I", data[idx - 4:idx])[0]
        if 20 < box_size < len(data) and box_size > 12:
            payload = data[idx + 4: idx - 4 + box_size]
            if len(payload) > 8:
                if payload[:2] in (b"MM", b"II") and payload[2:4] in (b"\x00\x2a", b"\x2a\x00"):
                    return payload
                if payload[4:6] in (b"MM", b"II"):
                    return payload[4:]
        idx = data.find(b"Exif", idx + 4)

    for marker in (b"MM\x00\x2a", b"II\x2a\x00"):
        idx = data.find(marker)
        if idx >= 0 and idx + 100 < len(data):
            return data[idx:]
    return None


def parse_tiff_user_comment(tiff: bytes) -> str | None:
    if len(tiff) < 8:
        return None

    if tiff[:2] == b"MM":
        endian = ">"
    elif tiff[:2] == b"II":
        endian = "<"
    else:
        return None

    magic = struct.unpack(f"{endian}H", tiff[2:4])[0]
    if magic != 42:
        return None

    ifd_offset = struct.unpack(f"{endian}I", tiff[4:8])[0]
    exif_ifd_offset = find_tag_in_ifd(tiff, ifd_offset, endian, 0x8769)
    if exif_ifd_offset is None:
        return None
    return read_user_comment_from_ifd(tiff, exif_ifd_offset, endian)


def find_tag_in_ifd(tiff: bytes, ifd_offset: int, endian: str, target_tag: int) -> int | None:
    if ifd_offset + 2 > len(tiff):
        return None

    num_entries = struct.unpack(f"{endian}H", tiff[ifd_offset:ifd_offset + 2])[0]
    if num_entries > 200:
        return None

    for i in range(num_entries):
        entry_pos = ifd_offset + 2 + i * 12
        if entry_pos + 12 > len(tiff):
            return None
        tag = struct.unpack(f"{endian}H", tiff[entry_pos:entry_pos + 2])[0]
        if tag == target_tag:
            return struct.unpack(f"{endian}I", tiff[entry_pos + 8:entry_pos + 12])[0]
    return None


def read_user_comment_from_ifd(tiff: bytes, ifd_offset: int, endian: str) -> str | None:
    if ifd_offset + 2 > len(tiff):
        return None

    num_entries = struct.unpack(f"{endian}H", tiff[ifd_offset:ifd_offset + 2])[0]
    if num_entries > 200:
        return None

    for i in range(num_entries):
        entry_pos = ifd_offset + 2 + i * 12
        if entry_pos + 12 > len(tiff):
            return None
        tag = struct.unpack(f"{endian}H", tiff[entry_pos:entry_pos + 2])[0]
        if tag != 0x9286:
            continue

        count = struct.unpack(f"{endian}I", tiff[entry_pos + 4:entry_pos + 8])[0]
        value_offset = struct.unpack(f"{endian}I", tiff[entry_pos + 8:entry_pos + 12])[0]
        if count <= 4:
            return None
        if value_offset + count > len(tiff):
            count = len(tiff) - value_offset
        uc_data = tiff[value_offset:value_offset + count]
        return decode_exif_user_comment(uc_data)
    return None
