"""Shared EXIF UserComment parsing helpers."""



def _exif_read_u16(b: bytes, off: int, le: bool) -> int:
    if off + 2 > len(b):
        return 0
    return int.from_bytes(b[off:off + 2], "little" if le else "big", signed=False)


def _exif_read_u32(b: bytes, off: int, le: bool) -> int:
    if off + 4 > len(b):
        return 0
    return int.from_bytes(b[off:off + 4], "little" if le else "big", signed=False)


def _parse_exif_user_comment(exif_bytes: bytes) -> str | None:
    """Best-effort EXIF parser to extract UserComment (0x9286)."""
    try:
        b = exif_bytes
        if b.startswith(b"Exif\x00\x00"):
            b = b[6:]
        if len(b) < 8:
            return None

        bo = b[:2]
        le = bo == b"II"
        if (not le) and bo != b"MM":
            return None
        if _exif_read_u16(b, 2, le) != 42:
            return None
        ifd0 = _exif_read_u32(b, 4, le)
        if ifd0 <= 0 or ifd0 + 2 > len(b):
            return None

        def _walk_ifd(ifd_off: int) -> bytes | None:
            if ifd_off + 2 > len(b):
                return None
            n = _exif_read_u16(b, ifd_off, le)
            base = ifd_off + 2
            for i in range(n):
                ent = base + 12 * i
                if ent + 12 > len(b):
                    break
                tag = _exif_read_u16(b, ent + 0, le)
                typ = _exif_read_u16(b, ent + 2, le)
                cnt = _exif_read_u32(b, ent + 4, le)
                val_off = ent + 8

                if tag == 0x8769 and typ == 4 and cnt == 1:
                    sub = _exif_read_u32(b, val_off, le)
                    got = _walk_ifd(sub)
                    if got:
                        return got

                if tag == 0x9286:
                    if cnt <= 4:
                        raw = b[val_off:val_off + cnt]
                    else:
                        off = _exif_read_u32(b, val_off, le)
                        if off <= 0 or off + cnt > len(b):
                            return None
                        raw = b[off:off + cnt]
                    return raw
            return None

        raw = _walk_ifd(ifd0)
        if not raw:
            return None

        # Delegate decoding to the shared, endianness-aware decoder.
        # That decoder includes the YU_META marker and prefers UTF-16-LE
        # (this project's writer) when neither/both markers match — matches
        # core/extractors/webp_novelai.py and exif_comment_decode.py paths.
        from core.extractors.exif_decode import decode_exif_user_comment
        s = decode_exif_user_comment(raw) or ""

        s = s.strip("\x00").strip()
        return s or None
    except Exception:
        return None
