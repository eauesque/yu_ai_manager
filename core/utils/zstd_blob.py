"""
zstd transparent compression utility.

Compresses TEXT columns as BLOB for storage.
Magic bytes b'\x28\xb5\x2f\xfd' identify zstd-compressed data.
Uncompressed data is also readable transparently (backward compatible during migration).

Usage:
    # Write
    blob = compress_text(my_string)       # bytes | None
    con.execute("UPDATE t SET col=? WHERE id=?", (blob, row_id))

    # Read
    text = decompress_blob(row["col"])    # str | None
"""
import zstandard as zstd

ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'
_MIN_LEN = 512  # Below this threshold, compression overhead is not worthwhile

# Thread-safe: ZstdCompressor/Decompressor instances are safe to share
_cctx = zstd.ZstdCompressor(level=3, threads=-1)
_dctx = zstd.ZstdDecompressor()


def compress_text(text: str | None) -> bytes | None:
    """TEXT -> zstd BLOB (bytes). Returns None for None input."""
    if text is None:
        return None
    raw = text.encode("utf-8")
    if len(raw) < _MIN_LEN:
        return raw          # Store short strings uncompressed (avoid overhead)
    return _cctx.compress(raw)


def decompress_blob(blob: bytes | str | None) -> str | None:
    """zstd BLOB / raw bytes / str -> str. Backward compatible."""
    if blob is None:
        return None
    if isinstance(blob, str):
        return blob                          # Legacy TEXT column data
    if blob[:4] == ZSTD_MAGIC:
        return _dctx.decompress(blob).decode("utf-8", errors="replace")
    return blob.decode("utf-8", errors="replace")  # Uncompressed bytes (short strings)
