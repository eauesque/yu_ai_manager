"""Folder dialog compatibility wrapper.

Implementation moved to ``core.platform.folder_dialog``. Keep this module only
for older import paths and tests that patch it directly.
"""


from core.platform import select_folder
from core.platform.folder_dialog import _decode_output  # noqa: F401 — test compatibility


def select_folder_dialog(initial_dir: str = "") -> dict[str, str | None | bool]:
    """Open an OS-native folder selection dialog."""
    return select_folder(initial_dir)
