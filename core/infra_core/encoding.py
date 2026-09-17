"""Encoding fallback chain for CJK archive filenames.

Provides a priority-ordered list of encodings to try when decoding
filenames from legacy archives (ZIP CP437 repair, 7z, NAS paths).

chardet/cchardet auto-detection is intentionally NOT used because
short filenames (10-30 bytes) produce too many false positives.
Instead we rely on a fixed priority order tuned for the JP-heavy
use-case of this project.
"""

import logging

logger = logging.getLogger(__name__)

# --- Encoding fallback chain ------------------------------------------
# Order: most common CJK encodings first, then other East Asian.
# UTF-8 is not in this list because zipfile handles it via flag bit 11
# before CP437 fallback even triggers.
ENCODING_FALLBACK_CHAIN: tuple[str, ...] = (
    "cp932",        # Shift-JIS, Japanese Windows (most common legacy)
    "euc-jp",       # Japanese Unix/Linux
    "iso-2022-jp",  # JIS code, 90s-era files
    "euc-kr",       # Korean Unix/Linux
    "cp949",        # Korean Windows (EUC-KR superset)
    "gb2312",       # Chinese Simplified (basic)
    "gbk",          # Chinese Simplified (Windows, GB2312 superset)
    "big5",         # Chinese Traditional
    "cp950",        # Chinese Traditional Windows (Big5 superset)
    "shift_jis",    # Alias for Shift-JIS (some tools use this name)
)

# Subset used for _repair_cp437_names (ZIP CP437 mojibake recovery).
# Slightly broader than ENCODING_FALLBACK_CHAIN — includes all aliases.
ZIP_REPAIR_ENCODINGS: tuple[str, ...] = ENCODING_FALLBACK_CHAIN

# Encodings to try as zipfile metadata_encoding (Python 3.11+).
# Only encodings that are common *single-byte supersets* or variable-length
# CJK encodings that won't corrupt ASCII-range bytes.
ZIP_METADATA_ENCODINGS: tuple[str, ...] = (
    "cp932",
    "euc-jp",
    "gbk",
    "euc-kr",
    "big5",
)


def try_decode(raw: bytes, label: str = "") -> tuple[str | None, str]:
    """Try decoding *raw* bytes using the fallback chain.

    Returns ``(decoded_string, encoding_name)`` on success,
    or ``(None, "")`` if all encodings fail.
    Debug-logs each attempt when the logger is at DEBUG level.
    """
    for enc in ENCODING_FALLBACK_CHAIN:
        try:
            decoded = raw.decode(enc)
            logger.debug(
                "Encoding OK: %s -> %s%s",
                enc, decoded[:40], f" ({label})" if label else "",
            )
            return decoded, enc
        except (UnicodeDecodeError, LookupError):
            logger.debug(
                "Encoding FAIL: %s%s",
                enc, f" ({label})" if label else "",
            )
            continue
    return None, ""


def repair_cp437_name(name: str) -> list[str]:
    """Recover mojibake names caused by CP437 default decoding.

    Returns a list of successfully decoded alternatives (may be empty).
    """
    try:
        raw = name.encode("cp437")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return []

    results: list[str] = []
    for enc in ZIP_REPAIR_ENCODINGS:
        try:
            decoded = raw.decode(enc)
            if decoded != name and decoded not in results:
                results.append(decoded)
                logger.debug("CP437 repair: %s -> %r (%s)", name[:30], decoded[:30], enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return results
