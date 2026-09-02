"""Text and path helper functions."""

import os
import re
from pathlib import Path


def norm_space(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def split_namespace(tag: str) -> tuple[str | None, str]:
    if ":" in tag:
        ns, rest = tag.split(":", 1)
        ns = norm_space(ns)
        rest = norm_space(rest)
        if ns and rest:
            if re.match(r"^[\d.]+\)?$", rest):
                cleaned = re.sub(r":[\d.]+\)?$", "", norm_space(tag))
                return None, cleaned if cleaned else norm_space(tag)
            return ns, rest
    normed = norm_space(tag)
    if normed.startswith("@"):
        rest = norm_space(normed[1:])
        if rest and re.search(r"[^\W_]", rest):
            return "artist", rest
    return None, normed


def normalize_path(p: Path) -> str:
    """Normalize path. Delegates to core.platform."""
    from core.platform import normalize_path as _normalize
    return _normalize(p)


def resolve_real_path(path_str: str) -> str:
    """Resolve OS junctions/aliases and normalize. Delegates to core.platform."""
    from core.platform import resolve_real_path as _resolve
    return _resolve(path_str)


_ARCHIVE_EXTS = (".zip!", ".7z!", ".rar!")


def split_archive_path(path: str) -> tuple[str, str]:
    """Split ``archive.zip!internal/file.jpg`` into (archive, internal).

    Unlike ``path.split("!", 1)``, this correctly handles ``!`` in
    the archive filename by looking for ``.zip!`` or ``.7z!`` boundaries.

    For nested archives like ``outer.zip!inner.zip!path/img.png``,
    splits at the **first** boundary: ``outer.zip`` + ``inner.zip!path/img.png``.
    The caller (e.g. read_bytes_from_zip) handles the nested part.

    Returns ``(path, "")`` if no archive boundary is found.
    """
    lower = path.lower()
    # Split at the first archive boundary (nested ZIP support)
    first_idx = -1
    first_ext_len = 0
    for ext in _ARCHIVE_EXTS:
        idx = lower.find(ext)
        if idx >= 0 and (first_idx < 0 or idx < first_idx):
            first_idx = idx
            first_ext_len = len(ext)
    if first_idx >= 0:
        sep = first_idx + first_ext_len - 1  # position of '!'
        return path[:sep], path[sep + 1:]
    # No archive boundary: treat as a regular path. The previous fallback
    # of `path.split("!", 1)` mis-handled regular files whose folder or
    # filename contained '!' (e.g. "...エルフ! [同人cg集]\\img.jpg") — the
    # caller would treat the prefix as a (non-existent) archive.
    return path, ""


def is_archive_member(path: str) -> bool:
    """Return True if *path* looks like ``archive.zip!entry``."""
    lower = path.lower()
    return any(ext in lower for ext in _ARCHIVE_EXTS)


def archive_part(path: str) -> str:
    """Return the archive portion of an archive member path."""
    return split_archive_path(path)[0]


def sanitize_user_path(raw: str) -> str:
    if not raw:
        return raw

    raw = raw.replace("\t", "\\t")
    raw = raw.replace("\n", "\\n")
    raw = raw.replace("\r", "\\r")
    raw = raw.replace("\x00", "\\0")

    raw = raw.strip().strip('"').strip("'").strip()

    is_unc = raw.startswith("\\\\") or raw.startswith("//")
    result = os.path.normpath(raw)

    if is_unc and not (result.startswith("\\\\") or result.startswith("//")):
        result = "\\\\" + result.lstrip("\\").lstrip("/")

    return result
