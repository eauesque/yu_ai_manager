"""Thumbnail batch warmup -- re-export facade.

External-compatibility facade only.
Repo-internal imports should use the concrete implementation modules.

Split into:
  - thumbnail_batch_warmup_core: orchestration, locking, background launch
  - thumbnail_batch_warmup_archives: ZIP/7z/RAR specific warmup functions
"""

# Re-export all public symbols for backward compatibility
from core.files_core.thumbnail_batch_warmup_core import (  # noqa: F401
    _archive_done_cv_lock,
    _archive_done_cvs,
    _archive_locks,
    _cleanup_archive_lock,
    _get_archive_lock,
    _lock_guard,
    start_warmup_background,
    warmup_thumbnails_for_ids,
)
