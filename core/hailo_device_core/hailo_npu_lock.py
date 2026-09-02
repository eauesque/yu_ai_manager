"""Hailo NPU process-wide exclusion lock."""

import functools
import logging
import os
import sys
import time
import types
from pathlib import Path

try:
    import fcntl
except ModuleNotFoundError:
    import msvcrt

    _LOCK_OFFSET = 4096
    _LOCK_LEN = 1

    class _FcntlCompat(types.ModuleType):
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 8

        def flock(self, fd: int, operation: int) -> None:
            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            if operation & self.LOCK_UN:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_LEN)
                return
            if operation & self.LOCK_EX:
                mode = msvcrt.LK_NBLCK if operation & self.LOCK_NB else msvcrt.LK_LOCK
                msvcrt.locking(fd, mode, _LOCK_LEN)

    fcntl = _FcntlCompat("fcntl")
    sys.modules.setdefault("fcntl", fcntl)

logger = logging.getLogger(__name__)


class HailoNpuLock:
    """Process-wide exclusion lock for Hailo NPU operations.

    Features:
    - Non-blocking try_acquire() for quick checks
    - Blocking acquire(timeout) for sustained operations
    - Automatic stale lock cleanup (dead pid detection)
    - Context manager support
    - Lock file stores pid for debugging/cleanup
    """

    def __init__(self, timeout: float = 5.0):
        """Initialize lock with timeout in seconds.

        Args:
            timeout: Maximum time to wait for lock acquisition (seconds)
        """
        self.timeout = timeout
        self._lock_file_path = self._resolve_lock_file_path()
        self._lock_fd_path = self._resolve_lock_fd_path()
        self._fd: int | None = None
        logger.debug(f"HailoNpuLock initialized, lock file: {self._lock_file_path}")

    def _resolve_lock_fd_path(self) -> Path:
        if os.name != "nt":
            return self._lock_file_path
        return self._lock_file_path.with_name(self._lock_file_path.name + ".guard")

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _resolve_lock_file_path() -> Path:
        """Resolve lock file path: config runtime_dir or project root tmp/ (absolute).

        Returns absolute Path to lock file.
        """
        # Try to read from config if available
        lock_path = None
        try:
            from core.configuration import get_config  # type: ignore[import-not-found]
            config = get_config()
            if config and isinstance(config, dict):
                runtime_dir = config.get("paths", {}).get("runtime_dir")
                if runtime_dir:
                    lock_path = Path(runtime_dir) / "hailo_npu.lock"
        except Exception:
            logger.warning("hailo device step failed", exc_info=True)

        # Fallback to project root tmp/
        if not lock_path:
            try:
                # Try to find project root via git
                import subprocess
                result = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    cwd=os.path.dirname(__file__),
                )
                if result.returncode == 0:
                    project_root = Path(result.stdout.strip())
                    lock_path = project_root / "tmp" / "hailo_npu.lock"
            except Exception:
                logger.warning("hailo device step failed", exc_info=True)

        # Final fallback: use /tmp but ensure isolation per-project if needed
        if not lock_path:
            lock_path = Path(__file__).resolve().parents[2] / "tmp" / "hailo_npu.lock"

        # Ensure absolute path
        lock_path = lock_path.resolve()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        return lock_path

    def _read_lock_pid(self) -> int | None:
        """Read pid from lock file if it exists.

        Returns None if file doesn't exist or is empty.
        """
        try:
            if self._lock_file_path.exists():
                content = self._lock_file_path.read_text(encoding="utf-8").strip()
                if content and content.isdigit():
                    return int(content)
        except Exception as e:
            logger.debug(f"Error reading lock file: {e}")
        return None

    @staticmethod
    def _write_lock_pid_fd(fd: int, pid: int) -> None:
        """Write pid to an already-locked file descriptor."""
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(pid).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error writing to lock file: {e}")
            raise RuntimeError(f"Failed to write lock file: {e}") from e

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if process with given pid is still alive using os.kill(pid, 0)."""
        if os.name == "nt":
            try:
                import psutil

                return psutil.pid_exists(pid)
            except Exception:
                logger.warning("hailo device step failed", exc_info=True)
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            # Assume alive if we can't check (permission issue, different user, etc)
            return True

    def _cleanup_stale_lock(self) -> None:
        """Remove lock file if it contains a stale (dead) pid."""
        stored_pid = self._read_lock_pid()
        if stored_pid and not self._is_pid_alive(stored_pid):
            try:
                self._lock_file_path.unlink()
                if self._lock_fd_path != self._lock_file_path and self._lock_fd_path.exists():
                    self._lock_fd_path.unlink()
                logger.info(f"Cleaned up stale lock file (pid {stored_pid} dead)")
            except Exception as e:
                logger.debug(f"Error cleaning stale lock: {e}")

    def try_acquire(self) -> bool:
        """Non-blocking attempt to acquire the lock.

        Returns True if lock acquired, False if already held by another process.
        Does not raise.
        """
        if self._fd is not None:
            return True  # Already held by this process

        # Check for and clean stale locks first
        self._cleanup_stale_lock()

        try:
            fd = os.open(
                str(self._lock_fd_path),
                os.O_CREAT | os.O_WRONLY,
                0o644,
            )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                # Write our pid to the lock file
                if self._lock_fd_path == self._lock_file_path:
                    self._write_lock_pid_fd(fd, os.getpid())
                else:
                    self._lock_file_path.write_text(str(os.getpid()), encoding="utf-8")
                self._fd = fd
                logger.debug(f"Lock acquired (non-blocking) by pid {os.getpid()}")
                return True
            except OSError as e:
                # Lock is held by another process
                os.close(fd)
                logger.debug(f"Lock unavailable (held by another process): {e}")
                return False
        except Exception as e:
            logger.error(f"Error in try_acquire: {e}")
            return False

    def acquire(self) -> None:
        """Blocking acquire with timeout.

        Raises RuntimeError if timeout is exceeded.
        """
        if self._fd is not None:
            return  # Already held

        # Check for and clean stale locks first
        self._cleanup_stale_lock()

        start_time = time.monotonic()
        attempt = 0
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout:
                raise RuntimeError(
                    f"Failed to acquire Hailo NPU lock within {self.timeout}s. "
                    f"Another process may be using the Hailo device."
                )

            try:
                fd = os.open(
                    str(self._lock_fd_path),
                    os.O_CREAT | os.O_WRONLY,
                    0o644,
                )
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                    # Write our pid to the lock file
                    if self._lock_fd_path == self._lock_file_path:
                        self._write_lock_pid_fd(fd, os.getpid())
                    else:
                        self._lock_file_path.write_text(str(os.getpid()), encoding="utf-8")
                    self._fd = fd
                    logger.info(f"Lock acquired (blocking) by pid {os.getpid()} after {elapsed:.2f}s")
                    return
                except OSError:
                    os.close(fd)
                    # Lock held by another, try again
                    attempt += 1
                    remaining = self.timeout - elapsed
                    wait_time = min(0.1, remaining)
                    time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Error in acquire: {e}")
                raise RuntimeError(f"Failed to acquire Hailo NPU lock: {e}") from e

    def release(self) -> None:
        """Release the lock. Idempotent (safe to call multiple times)."""
        if self._fd is None:
            return  # Not held by this process

        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
            os.close(self._fd)
            self._fd = None
            logger.info(f"Lock released by pid {os.getpid()}")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")
            self._fd = None  # Mark as released anyway

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False
