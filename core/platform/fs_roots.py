"""Root directory enumeration.

Windows: Enumerate drive letters (A:-Z:)
Unix:    ["/"]
"""

import os

from .detect import is_windows


def list_roots() -> list[str]:
    """Return the system root directories."""
    if is_windows():
        return _windows_roots()
    return ["/"]


def _windows_roots() -> list[str]:
    """Enumerate Windows drive letters."""
    roots = []
    for i in range(ord("A"), ord("Z") + 1):
        drive = f"{chr(i)}:\\"
        if os.path.isdir(drive):
            roots.append(drive)
    return roots
