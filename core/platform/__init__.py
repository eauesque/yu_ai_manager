"""Platform abstraction package.

All OS-specific branching is accessed via this package.
"""

from .asyncio_proactor_patch import install_proactor_connection_reset_silencer
from .detect import CURRENT_OS, OSType, detect_os, is_linux, is_macos, is_windows, platform_display_name
from .file_lock import lock_file, unlock_file
from .file_manager import open_in_file_manager
from .folder_dialog import select_folder
from .fs_roots import list_roots
from .nvidia_dll import register_nvidia_dll_dirs
from .path_normalize import normalize_path, resolve_real_path
from .port_cleanup import kill_stale_port
from .process_restart import exec_restart
from .signal_handler import install_sigint_handler
from .ssl_certs import ensure_ssl_certs

__all__ = [
    "CURRENT_OS",
    "OSType",
    "detect_os",
    "ensure_ssl_certs",
    "exec_restart",
    "install_proactor_connection_reset_silencer",
    "install_sigint_handler",
    "is_linux",
    "is_macos",
    "is_windows",
    "kill_stale_port",
    "list_roots",
    "lock_file",
    "normalize_path",
    "platform_display_name",
    "open_in_file_manager",
    "register_nvidia_dll_dirs",
    "resolve_real_path",
    "select_folder",
    "unlock_file",
]
