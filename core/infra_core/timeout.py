"""Timeout wrapper for blocking I/O operations.

Runs the target function in a daemon thread so the caller can
move on after *timeout* seconds even when the underlying I/O
(e.g. opening a ZIP on a slow/dying drive) blocks indefinitely.

The daemon thread keeps running in the background but will not
prevent interpreter shutdown.
"""

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

# Default timeout for archive listing during the counting phase.
ARCHIVE_LIST_TIMEOUT = 30  # seconds

# Default timeout for single-file scan operations (mtime/size/metadata/hash).
ARCHIVE_SCAN_TIMEOUT = 60  # seconds

# ---------------------------------------------------------------------------
# Archive resource limits — OOM / resource exhaustion prevention
# ---------------------------------------------------------------------------

# Max size per entry read (decompressed size)
ARCHIVE_MAX_ENTRY_SIZE = 512 * 1024 * 1024  # 512 MB

# Cumulative memory limit for batch reads
ARCHIVE_MAX_BATCH_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB

# Max entries per chunk in scan batch
ARCHIVE_SCAN_CHUNK_SIZE = 200

# Total size limit for batch ZIP downloads
ARCHIVE_MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


def run_with_timeout(func: Callable[..., T], timeout: float, label: str = "") -> T:
    """Execute *func()* in a daemon thread with a timeout.

    Returns the function result on success.
    Raises ``TimeoutError`` if *timeout* seconds elapse before completion.
    Re-raises any exception thrown by *func*.
    """
    result: list[Any] = [None]
    error: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result[0] = func()
        except BaseException as exc:
            error[0] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        desc = f" ({label})" if label else ""
        raise TimeoutError(
            f"Operation timed out after {timeout}s{desc}"
        )
    if error[0] is not None:
        raise error[0]
    return result[0]  # type: ignore[return-value]
