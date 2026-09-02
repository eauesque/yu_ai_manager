"""Self-update backend: detect install type, check for updates, apply git updates."""

from core.update_core.detect import detect_install_type
from core.update_core.git_updater import run_git_update
from core.update_core.portable_updater import run_portable_update
from core.update_core.pre_update_backup import create_pre_update_backup
from core.update_core.unified_manager import (
    apply_unified_updates,
    backup_extension_configs,
    check_unified_updates,
)
from core.update_core.version_check import check_for_update
