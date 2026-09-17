"""Execution loop helpers — IO priority, constants, archive batching."""

import logging

from core.helpers_core.helpers_text_path import archive_part, is_archive_member

logger = logging.getLogger(__name__)


def _lower_io_priority() -> None:
    """Lower I/O priority for the scan thread (best-effort)."""
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadPriority(handle, -1)  # BELOW_NORMAL
        except Exception:
            logger.debug("scan step failed", exc_info=True)
    elif sys.platform != "darwin":
        try:
            import os as _os
            _os.nice(5)
        except Exception:
            logger.debug("scan step failed", exc_info=True)

# -- Tuning constants ---------------------------------------------------------

PROGRESS_THROTTLE = 2.0  # seconds between progress events

COMMIT_INTERVAL = 20       # DB commit interval (reduced from 200 to 20 to mitigate WAL lock contention)
ARCHIVE_COMMIT_INTERVAL = 100  # Commit interval for archive members (reduce I/O load)
STATE_SAVE_INTERVAL = 100  # scan_state save interval (less frequent than commit for I/O cost)
WAL_CHECKPOINT_INTERVAL = 2000  # WAL checkpoint interval (prevent WAL bloat)

# If a single scan_one() call takes longer than this, log a loud warning.
# Individual I/O ops inside already have their own timeouts (30-60s), so
# exceeding this budget means something unexpected is happening.
SLOW_ENTRY_WARN = 120.0  # seconds


def should_compute_hash(config, *, explicit: bool) -> bool:
    """Hash computation is on-demand only: require explicit opt-in."""
    return bool(explicit and bool(config.get("compute_hash", False)))


def collect_archive_batch(file_queue) -> tuple[str, list[str], list[str]]:
    """Collect consecutive archive members from the same archive.

    Peeks ahead in the queue and collects all entries belonging to the
    same archive file.  Returns (archive_path, internal_paths, full_paths).

    Entries exceeding ARCHIVE_SCAN_CHUNK_SIZE remain in the queue and
    will be batched in the next iteration, keeping memory usage bounded.
    """
    from core.helpers_core.helpers_text_path import split_archive_path
    from core.infra_core.timeout import ARCHIVE_SCAN_CHUNK_SIZE

    first = file_queue.popleft()
    arc, ip = split_archive_path(first)
    internal_paths = [ip]
    full_paths = [first]

    while file_queue and len(internal_paths) < ARCHIVE_SCAN_CHUNK_SIZE:
        nxt = file_queue[0]
        if not isinstance(nxt, str) or not is_archive_member(nxt):
            break
        nxt_arc = archive_part(nxt)
        if nxt_arc != arc:
            break
        file_queue.popleft()
        _, nxt_ip = split_archive_path(nxt)
        internal_paths.append(nxt_ip)
        full_paths.append(nxt)

    return arc, internal_paths, full_paths
