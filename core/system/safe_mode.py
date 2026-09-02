"""Safe Mode detection and marker lifecycle.

Safe Mode activation is intentionally limited to the ``--safe-mode`` command
line flag. Do not add environment-variable or config-file activation paths.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SAFE_MODE_FLAG = "--safe-mode"
SAFE_MODE_MARKER_NAME = ".safe_mode_marker"


def is_safe_mode() -> bool:
    """Return True only when ``--safe-mode`` is present in ``sys.argv``."""
    return SAFE_MODE_FLAG in sys.argv[1:]


@dataclass(frozen=True)
class SafeModeManager:
    """Manage Safe Mode startup marker state."""

    data_dir: Path | None = None

    def is_active(self) -> bool:
        return is_safe_mode()

    def marker_path(self) -> Path:
        data_dir = self.data_dir
        if data_dir is None:
            from core.paths import get_data_dir

            data_dir = get_data_dir()
        return Path(data_dir) / SAFE_MODE_MARKER_NAME

    def marker_exists(self) -> bool:
        return self.marker_path().is_file()

    def mark_safe_mode_active(self) -> Path:
        marker = self.marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("safe-mode\n", encoding="utf-8")
        return marker

    def mark_safe_mode_inactive(self) -> None:
        self.marker_path().unlink(missing_ok=True)

    def sync_startup_marker(self) -> None:
        if self.is_active():
            self.mark_safe_mode_active()
        else:
            self.mark_safe_mode_inactive()


def mark_safe_mode_active() -> Path:
    return SafeModeManager().mark_safe_mode_active()


def mark_safe_mode_inactive() -> None:
    SafeModeManager().mark_safe_mode_inactive()
