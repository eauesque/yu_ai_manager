"""Low-level EXIF UserComment decoder."""


# Markers that indicate a successfully-decoded SD/NAI/ComfyUI generation comment.
# Used to disambiguate UTF-16 endianness when no BOM is present (the EXIF spec
# does not pin endian for UNICODE UserComment, and writers in the wild differ:
# this project itself writes UTF-16-LE via core/bridge_core/bridge_save.py).
_UC_MARKERS = (
    "YU_META",
    "Steps:",
    "Negative prompt:",
    "Sampler:",
    '"prompt":',
    '"sampler"',
    '"parameters"',
    "Description:",
)


def _decode_unicode_user_comment(payload: bytes) -> str | None:
    if payload[:2] == b"\xff\xfe":
        return payload[2:].decode("utf-16-le", errors="replace").rstrip("\x00")
    if payload[:2] == b"\xfe\xff":
        return payload[2:].decode("utf-16-be", errors="replace").rstrip("\x00")
    s_le = payload.decode("utf-16-le", errors="replace").rstrip("\x00")
    s_be = payload.decode("utf-16-be", errors="replace").rstrip("\x00")
    le_hit = any(m in s_le for m in _UC_MARKERS)
    be_hit = any(m in s_be for m in _UC_MARKERS)
    if le_hit and not be_hit:
        return s_le
    if be_hit and not le_hit:
        return s_be
    # Neither or both matched — prefer LE (matches this project's writer and
    # most modern tooling) unless it produced more replacement chars.
    if s_le.count("�") <= s_be.count("�"):
        return s_le
    return s_be


def decode_exif_user_comment(raw: bytes) -> str | None:
    if not raw or len(raw) < 9:
        return None

    prefix = raw[:8]
    if prefix == b"UNICODE\x00":
        text = _decode_unicode_user_comment(raw[8:])
        return text if text and text.strip() else None
    if prefix[:5] == b"ASCII":
        text = raw[8:].decode("ascii", errors="replace").rstrip("\x00")
        return text if text.strip() else None
    if prefix == b"\x00" * 8:
        text = raw[8:].decode("utf-8", errors="replace").rstrip("\x00")
        return text if text.strip() else None
    text = raw.decode("utf-8", errors="replace").rstrip("\x00")
    return text if text.strip() else None
