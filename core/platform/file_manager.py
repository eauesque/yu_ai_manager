"""Open a folder in the OS-native file manager."""

import os
import re
import subprocess

from .detect import CURRENT_OS, OSType

# Regex to detect null bytes and control characters (except tab/newline)
_UNSAFE_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _validate_file_path(file_path: str) -> str:
    """Validate file path safety.

    - Reject null bytes and control characters
    - Verify the path exists
    """
    if _UNSAFE_CHARS_RE.search(file_path):
        raise ValueError(
            "Path contains null byte or control characters"
        )
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Path does not exist: {abs_path}")
    return abs_path


def open_in_file_manager(file_path: str) -> None:
    """Open the parent folder of a file in the native file manager.

    Windows: explorer /select, <path>
    macOS:   open -R <path>
    Linux:   xdg-open <dir>
    """
    abs_path = _validate_file_path(file_path)

    if CURRENT_OS is OSType.WINDOWS:
        subprocess.run(["explorer", "/select,", abs_path])
    elif CURRENT_OS is OSType.MACOS:
        subprocess.run(["open", "-R", abs_path])
    else:
        dir_path = os.path.dirname(abs_path)
        subprocess.run(["xdg-open", dir_path])
