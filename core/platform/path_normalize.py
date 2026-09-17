"""Platform abstraction for path normalization."""

import os
from pathlib import Path

from .detect import is_windows


def normalize_path(p: Path) -> str:
    """Normalize a path. Also applies normcase on Windows."""
    s = str(p)
    is_unc = s.startswith("\\\\") or s.startswith("//")
    if is_unc:
        s = os.path.normpath(s)
    else:
        s = os.path.abspath(s)
        s = os.path.normpath(s)
    if is_windows():
        s = os.path.normcase(s)
    return s


def resolve_real_path(path_str: str) -> str:
    """Resolve OS junctions/aliases then apply normcase.

    Normalize Windows Japanese junctions (C:\\ユーザー -> C:\\Users)
    via Path.resolve() (GetFinalPathNameByHandleW).
    UNC paths fall back to normpath due to known issues with Path.resolve().
    """
    is_unc = path_str.startswith("\\\\") or path_str.startswith("//")
    if is_unc:
        return os.path.normcase(os.path.normpath(path_str))
    try:
        resolved = str(Path(path_str).resolve())
        return os.path.normcase(os.path.normpath(resolved))
    except (OSError, ValueError):
        return os.path.normcase(os.path.normpath(path_str))
