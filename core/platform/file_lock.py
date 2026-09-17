"""OS-specific file locking.

Windows uses msvcrt, Unix uses fcntl.
"""

import contextlib

from .detect import is_windows

if is_windows():
    import msvcrt

    # msvcrt.locking requires byte count. 1MB covers a sufficient range.
    _LOCK_LEN = 1024 * 1024

    def lock_file(f) -> None:
        """Acquire an exclusive lock (Windows: msvcrt)."""
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, _LOCK_LEN)

    def unlock_file(f) -> None:
        """Release the lock (Windows: msvcrt)."""
        with contextlib.suppress(OSError):
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, _LOCK_LEN)
else:
    import fcntl

    def lock_file(f) -> None:
        """Acquire an exclusive lock (Unix: fcntl)."""
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def unlock_file(f) -> None:
        """Release the lock (Unix: fcntl)."""
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
