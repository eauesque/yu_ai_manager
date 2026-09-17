"""File hashing helpers used by scanners."""

import contextlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def file_etag(path: Path) -> str:
    """ETag equivalent (extension-specific policy, approximate).

    Policy (recommended values):
      JPG : threshold=2MB,  chunk=256KB, head+tail
      PNG : threshold=2MB,  chunk=512KB, head+tail
      WEBM: threshold=4MB,  chunk=512KB, head+mid+tail
    """
    import hashlib

    st = path.stat()
    size = int(st.st_size)
    ext = path.suffix.lower()

    if ext in (".jpg", ".jpeg"):
        full_threshold = 2_000_000
        chunk_size = 256_000
        use_mid = False
    elif ext == ".png":
        full_threshold = 2_000_000
        chunk_size = 512_000
        use_mid = False
    elif ext == ".webm":
        full_threshold = 4_000_000
        chunk_size = 512_000
        use_mid = True
    else:
        full_threshold = 2_000_000
        chunk_size = 256_000
        use_mid = False

    h = hashlib.sha256()
    h.update(str(size).encode("ascii"))
    h.update(ext.encode("ascii", errors="ignore"))

    def _read_full(f) -> None:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)

    with path.open("rb") as f:
        if size <= full_threshold:
            _read_full(f)
        else:
            h.update(f.read(chunk_size))
            if use_mid and size > (chunk_size * 3):
                try:
                    mid = max(0, (size // 2) - (chunk_size // 2))
                    f.seek(mid)
                    h.update(f.read(chunk_size))
                except Exception as exc:
                    logger.debug("Mid-seek hash read failed: %s", exc)
            try:
                if size > chunk_size:
                    f.seek(max(0, size - chunk_size))
                    h.update(f.read(chunk_size))
            except Exception:
                f.seek(0)
                _read_full(f)

    return h.hexdigest()


def bytes_etag(data: bytes, filename: str) -> str:
    """ETag from in-memory bytes (ZIP/7z members). Same policy as file_etag."""
    import hashlib

    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    size = len(data)

    if ext in (".jpg", ".jpeg"):
        full_threshold, chunk_size, use_mid = 2_000_000, 256_000, False
    elif ext == ".png":
        full_threshold, chunk_size, use_mid = 2_000_000, 512_000, False
    elif ext == ".webm":
        full_threshold, chunk_size, use_mid = 4_000_000, 512_000, True
    else:
        full_threshold, chunk_size, use_mid = 2_000_000, 256_000, False

    h = hashlib.sha256()
    h.update(str(size).encode("ascii"))
    h.update(ext.encode("ascii", errors="ignore"))

    if size <= full_threshold:
        h.update(data)
    else:
        h.update(data[:chunk_size])
        if use_mid and size > chunk_size * 3:
            mid = max(0, (size // 2) - (chunk_size // 2))
            h.update(data[mid:mid + chunk_size])
        if size > chunk_size:
            h.update(data[max(0, size - chunk_size):])

    return h.hexdigest()


def stream_etag(stream, filename: str, size: int | None = None) -> str:
    """ETag from a file-like object without loading the whole payload in memory.

    If the stream is seekable, uses the same sampling policy as ``file_etag``.
    Otherwise falls back to a full streaming hash.
    """
    import hashlib

    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext in (".jpg", ".jpeg"):
        full_threshold, chunk_size, use_mid = 2_000_000, 256_000, False
    elif ext == ".png":
        full_threshold, chunk_size, use_mid = 2_000_000, 512_000, False
    elif ext == ".webm":
        full_threshold, chunk_size, use_mid = 4_000_000, 512_000, True
    else:
        full_threshold, chunk_size, use_mid = 2_000_000, 256_000, False

    h = hashlib.sha256()
    if size is None:
        try:
            cur = stream.tell()
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(cur)
        except Exception:
            size = 0
    h.update(str(size).encode("ascii"))
    h.update(ext.encode("ascii", errors="ignore"))

    def _read_full() -> None:
        while True:
            b = stream.read(1024 * 1024)
            if not b:
                break
            h.update(b)

    try:
        stream.seek(0)
        seekable = True
    except Exception:
        seekable = False

    if (not seekable) or size <= full_threshold:
        _read_full()
        return h.hexdigest()

    h.update(stream.read(chunk_size))
    if use_mid and size > (chunk_size * 3):
        try:
            mid = max(0, (size // 2) - (chunk_size // 2))
            stream.seek(mid)
            h.update(stream.read(chunk_size))
        except Exception as exc:
            logger.debug("Mid-seek stream hash read failed: %s", exc)
            with contextlib.suppress(Exception):
                stream.seek(0)
            _read_full()
            return h.hexdigest()
    try:
        if size > chunk_size:
            stream.seek(max(0, size - chunk_size))
            h.update(stream.read(chunk_size))
    except Exception:
        with contextlib.suppress(Exception):
            stream.seek(0)
        _read_full()

    return h.hexdigest()
