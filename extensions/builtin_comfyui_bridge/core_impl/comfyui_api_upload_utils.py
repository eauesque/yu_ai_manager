"""Upload helpers for the ComfyUI bridge API."""

from pathlib import Path


def read_upload_bytes_limited(storage, *, max_bytes: int, chunk_size: int) -> bytes:
    """Read an uploaded file in chunks and reject oversized payloads."""
    stream = getattr(storage, "stream", storage)
    # Some ASGI/WSGI wrappers leave the stream position mid-read after
    # content-type parsing; seek to the start if supported.
    if hasattr(stream, "seek"):
        import contextlib
        with contextlib.suppress(OSError):
            stream.seek(0)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"image exceeds {max_bytes:,} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_image_filename(filename: str, *, allowed_exts) -> str:
    """Allow only the image formats supported by workflow extraction/upload."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext not in allowed_exts:
        raise ValueError(f"Unsupported format: {ext or 'unknown'}")
    return ext
