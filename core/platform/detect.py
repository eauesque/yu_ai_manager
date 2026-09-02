"""Unified OS detection module.

All platform branching references this ``CURRENT_OS``.
"""

import enum
import sys


class OSType(enum.Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


def detect_os() -> OSType:
    """Detect and return the current OS."""
    if sys.platform == "win32":
        return OSType.WINDOWS
    if sys.platform == "darwin":
        return OSType.MACOS
    return OSType.LINUX


CURRENT_OS = detect_os()

# Display names compatible with platform.system() ("Windows", "Darwin", "Linux")
_DISPLAY_NAMES = {
    OSType.WINDOWS: "Windows",
    OSType.MACOS: "Darwin",
    OSType.LINUX: "Linux",
}


def platform_display_name() -> str:
    """Return a string equivalent to platform.system() (for API compatibility)."""
    return _DISPLAY_NAMES[CURRENT_OS]


def is_windows() -> bool:
    return CURRENT_OS is OSType.WINDOWS


def is_macos() -> bool:
    return CURRENT_OS is OSType.MACOS


def is_linux() -> bool:
    return CURRENT_OS is OSType.LINUX
