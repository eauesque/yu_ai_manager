"""Helpers for bounded upload reads."""

from __future__ import annotations

import contextlib
import os
import tempfile

_READ_CHUNK_SIZE = 1024 * 1024


def read_upload_bytes_limited(storage, *, max_bytes: int) -> bytes:
    """Read an uploaded file in chunks and reject oversized payloads."""
    stream = getattr(storage, "stream", storage)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"file exceeds {max_bytes:,} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def copy_upload_to_temp(
    storage,
    *,
    max_bytes: int,
    suffix: str = "",
    prefix: str = "yu_upload_",
) -> str:
    """Stream an uploaded file into a temp path and enforce a hard size cap."""
    stream = getattr(storage, "stream", storage)
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    total = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = stream.read(_READ_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"file exceeds {max_bytes:,} byte limit")
                handle.write(chunk)
        return path
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
