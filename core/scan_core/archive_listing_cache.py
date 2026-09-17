"""Archive listing cache -- skip re-listing unchanged ZIP/7z archives.

Stores each archive's filesystem mtime + size alongside its known
member image paths.  On the next scan, if the archive's stat hasn't
changed, the cached member list is returned without opening the
archive -- saving significant I/O on large collections.

Persistence: JSON file (atomic write via tempfile + os.replace).
"""

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE_PATH = _PROJECT_ROOT / "core" / "scan_state.json"


class ArchiveListingCache:
    """In-memory cache backed by a JSON file."""

    def __init__(self, cache_path: Path | None = None):
        self._path = cache_path or _DEFAULT_CACHE_PATH
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._hits = 0
        self._misses = 0
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            if self._path.is_file():
                with open(self._path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    self._data = raw
                    logger.debug(
                        "Archive listing cache loaded: %d entries",
                        len(self._data),
                    )
        except Exception as e:
            logger.warning("Failed to load archive listing cache: %s", e)
            self._data = {}

    def save(self) -> None:
        """Persist cache to disk (atomic write)."""
        if not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False)
                os.replace(tmp, self._path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
            self._dirty = False
            logger.info(
                "Archive listing cache saved: %d entries "
                "(hits=%d, misses=%d)",
                len(self._data),
                self._hits,
                self._misses,
            )
        except Exception as e:
            logger.warning("Failed to save archive listing cache: %s", e)

    # ------------------------------------------------------------------
    # Lookup / update
    # ------------------------------------------------------------------

    def get_members(
        self, archive_path: str, current_mtime: int, current_size: int
    ) -> list[str] | None:
        """Return cached member paths if archive is unchanged, else None."""
        entry = self._data.get(archive_path)
        if entry is None:
            self._misses += 1
            return None
        if (
            entry.get("mtime") != current_mtime
            or entry.get("size") != current_size
        ):
            self._misses += 1
            return None
        members = entry.get("members")
        if members is None:
            self._misses += 1
            return None
        self._hits += 1
        return members

    def get_members_info(
        self, archive_path: str, current_mtime: int, current_size: int
    ) -> dict[str, list] | None:
        """Return cached per-member info {name: [mtime, size]} if available.

        Returns None if the archive is not cached, has changed, or if
        members_info was not stored (legacy cache entry).
        """
        entry = self._data.get(archive_path)
        if entry is None:
            return None
        if (
            entry.get("mtime") != current_mtime
            or entry.get("size") != current_size
        ):
            return None
        return entry.get("members_info")

    def is_archive_unchanged(self, archive_path: str) -> bool:
        """Check if archive's current stat matches cache (no stat() call).

        Uses the stored mtime/size — the caller must have previously
        verified via get_members() that the archive is unchanged.
        Returns True only if the archive has a cache entry with members_info.
        """
        entry = self._data.get(archive_path)
        if entry is None:
            return False
        return entry.get("members_info") is not None

    def update(
        self,
        archive_path: str,
        mtime: int,
        size: int,
        members: list[str],
        members_info: dict[str, list] | None = None,
    ) -> None:
        """Store/update archive listing.

        *members_info* is an optional dict mapping member name to
        ``[mtime, size]`` for Phase 1 skip optimisation.
        """
        entry: dict = {
            "mtime": mtime,
            "size": size,
            "members": members,
        }
        if members_info is not None:
            entry["members_info"] = members_info
        self._data[archive_path] = entry
        self._dirty = True

    def remove_stale(self, existing_archives: set) -> None:
        """Remove entries for archives no longer found on disk."""
        stale = [k for k in self._data if k not in existing_archives]
        for k in stale:
            del self._data[k]
        if stale:
            self._dirty = True
            logger.debug(
                "Archive listing cache: pruned %d stale entries", len(stale)
            )
