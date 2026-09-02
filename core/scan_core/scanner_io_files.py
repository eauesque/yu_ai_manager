"""File enumeration utilities for scanner I/O.

Provides iter_files() for walking directories with extension filtering,
symlink skipping, directory exclusion, and cancellation support.
"""

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

# Callback type for archive/file enumeration errors.
# Signature: on_error(path: str, error_type: str, detail: str)
ErrorCallback = Callable[[str, str, str], None] | None

# macOS-style bundle directory suffixes. Treated as opaque packages on the
# Mac filesystem and almost never contain user-managed images that should
# be tagged. The Music app's ``*.musiclibrary/artwork/`` (cover-art cache)
# and Photos app's ``*.photoslibrary`` are the typical offenders that
# yield "image found but cannot be written / cannot survive a re-scan"
# errors when WD-Tagger tries to merge XMP back into them. Match by suffix
# (case-insensitive) on any parent directory part.
_BUNDLE_SUFFIXES: frozenset[str] = frozenset({
    ".musiclibrary",
    ".photoslibrary",
    ".app",
    ".framework",
    ".bundle",
    ".lproj",
})


def iter_files(
    root: Path,
    recursive: bool,
    exts: Sequence[str],
    exclude_dirs: Sequence[str] = (),
    stop_event: threading.Event | None = None,
    on_error: ErrorCallback = None,
) -> Iterable[Path]:
    """Enumerate files under *root* that match the given extensions.

    Skips symlinks, honours exclude_dirs, and periodically checks
    stop_event for cooperative cancellation.
    """
    exclude_set = frozenset(exclude_dirs) if exclude_dirs else frozenset()
    _count = 0
    _CHECK_INTERVAL = 500
    try:
        if recursive:
            for p in root.rglob("*"):
                if stop_event is not None:
                    _count += 1
                    if _count % _CHECK_INTERVAL == 0 and stop_event.is_set():
                        return
                try:
                    # Skip symlinks (prevent link loops and traversal)
                    if p.is_symlink():
                        continue
                    if _is_excluded(p, root, exclude_set):
                        continue
                    if p.is_file() and p.suffix.lower() in exts:
                        yield p
                except (PermissionError, OSError) as e:
                    # Encoding errors from NAS/UNC/Samba paths surface as OSError
                    if on_error is not None:
                        on_error(str(p), "filesystem", str(e))
                    continue
        else:
            for p in root.glob("*"):
                if stop_event is not None:
                    _count += 1
                    if _count % _CHECK_INTERVAL == 0 and stop_event.is_set():
                        return
                try:
                    if p.is_symlink():
                        continue
                    if p.is_file() and p.suffix.lower() in exts:
                        yield p
                except (PermissionError, OSError) as e:
                    if on_error is not None:
                        on_error(str(p), "filesystem", str(e))
                    continue
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory {root}: {e}")
        if on_error is not None:
            on_error(str(root), "filesystem", f"Cannot access directory: {e}")


def _is_excluded(p: Path, root: Path, exclude_set: frozenset) -> bool:
    """Skip *p* when a parent directory matches *exclude_set* by name or
    has a macOS-style bundle suffix (e.g. ``.musiclibrary``, ``.app``)."""
    try:
        rel = p.relative_to(root)
    except ValueError:
        return False
    parents = rel.parts[:-1]
    if exclude_set and any(part in exclude_set for part in parents):
        return True
    # Path("foo.bar.app").suffix → ".app". Empty suffix returns "" so plain
    # directory names like "Documents" never match a bundle suffix.
    return any(
        Path(part).suffix.lower() in _BUNDLE_SUFFIXES for part in parents
    )
