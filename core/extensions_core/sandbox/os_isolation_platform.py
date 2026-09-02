"""Platform-specific OS isolation: macOS sandbox-exec, Windows, and common interface.

Provides the apply_os_isolation() entry point that dispatches to the
appropriate platform backend, plus get_os_isolation_info() for the API.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from .os_isolation_apparmor import (
    build_apparmor_command,
    build_setup_guidance,
    check_apparmor_kernel,
    generate_apparmor_profile,
    is_apparmor_available,
    is_apparmor_sudoers_configured,
    load_apparmor_profile,
    unload_apparmor_profile,
)

logger = logging.getLogger(__name__)

IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


# ── macOS sandbox-exec (experimental) ─────────────────────────


def is_sandbox_exec_available() -> bool:
    """Check whether macOS sandbox-exec is available (deprecated)."""
    if not IS_MACOS:
        return False
    return shutil.which("sandbox-exec") is not None


def build_sandbox_exec_command(
    cmd: list[str],
    ext_name: str,
    ext_dir: Path,
    permissions: set,
) -> list[str]:
    """Build a sandbox-exec prefixed command (macOS)."""
    from .os_isolation_profiles import build_seatbelt_profile

    profile_content = build_seatbelt_profile(
        ext_name=ext_name,
        ext_dir=ext_dir,
        permissions=permissions,
    )
    from .os_isolation_apparmor import _private_profile_dir

    profile_dir = _private_profile_dir("yu_ai_sandbox")
    safe = ext_name.replace("-", "_")
    profile_path = profile_dir / f"{safe}.sb"
    profile_path.write_text(profile_content, encoding="utf-8")

    return ["sandbox-exec", "-f", str(profile_path)] + cmd


# ── Windows helpers ──────────────────────────────────


def _get_windows_creation_flags(os_config) -> int:
    """Build Windows process creation flags."""
    flags = 0
    if IS_WINDOWS:
        # BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        flags = 0x4000
    return flags


# ── Common interface ──────────────────────────────────


def apply_os_isolation(
    cmd: list[str],
    env: dict[str, str],
    ext_name: str,
    ext_dir: Path,
    permissions: set,
    config: dict,
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Apply OS-level isolation and return (cmd, env, extra_popen_kwargs).

    Returns the input unchanged if OS isolation is not applicable.
    """
    from .os_isolation import load_os_isolation_config

    os_config = load_os_isolation_config(config)
    extra_kwargs: dict[str, Any] = {}

    if not os_config.enabled:
        return cmd, env, extra_kwargs

    applied = False

    if IS_LINUX and os_config.apparmor:
        applied = _apply_linux_isolation(
            cmd, env, ext_name, ext_dir, permissions, config,
        )
        if applied:
            cmd = build_apparmor_command(cmd, ext_name)
            env["YU_ISO_APPARMOR"] = "1"

    elif IS_MACOS:
        if os_config.macos_sandbox_exec and is_sandbox_exec_available():
            cmd = build_sandbox_exec_command(
                cmd, ext_name, ext_dir, permissions,
            )
            env["YU_ISO_SANDBOX_EXEC"] = "1"
            applied = True

    elif IS_WINDOWS:
        if os_config.windows_job_object:
            extra_kwargs["creationflags"] = (
                _get_windows_creation_flags(os_config)
            )
            env["YU_ISO_WIN_RESTRICTED"] = "1"
            applied = True

    if applied:
        if IS_LINUX and env.get("YU_ISO_APPARMOR") == "1":
            env["YU_ISO_OS_ENFORCED"] = "1"
        logger.info(f"{ext_name}: OS-level isolation applied")
    else:
        logger.debug(f"{ext_name}: OS isolation unavailable or skipped")

    return cmd, env, extra_kwargs


def _apply_linux_isolation(
    cmd: list[str],
    env: dict[str, str],
    ext_name: str,
    ext_dir: Path,
    permissions: set,
    config: dict,
) -> bool:
    """Apply Linux AppArmor isolation."""
    if not is_apparmor_available():
        logger.info(
            f"{ext_name}: AppArmor unavailable (kernel or tools not installed)"
        )
        return False

    scan_roots = [
        r.get("path", r) if isinstance(r, dict) else r
        for r in config.get("scan_roots", [])
    ]
    db_path = _get_db_path()
    if {"db:read", "db:write"} & permissions and db_path is None:
        logger.warning("%s: DB path unavailable for AppArmor protection", ext_name)
        return False
    profile_content = generate_apparmor_profile(
        ext_name=ext_name,
        ext_dir=ext_dir,
        permissions=permissions,
        scan_roots=scan_roots,
        db_path=db_path,
    )
    return load_apparmor_profile(ext_name, profile_content)


def _get_db_path() -> Path | None:
    try:
        from core.services_core.db_api import get_db_path
        return get_db_path()
    except Exception:
        return None


def cleanup_os_isolation(ext_name: str) -> None:
    """Clean up OS isolation resources when an extension stops."""
    if IS_LINUX:
        unload_apparmor_profile(ext_name)


def get_os_isolation_info() -> dict:
    """Return OS isolation availability info (for API responses)."""
    info: dict[str, Any] = {
        "platform": sys.platform,
        "available": False,
        "method": None,
        "details": {},
    }

    if IS_LINUX:
        aa_available = is_apparmor_available()
        aa_tools = shutil.which("aa-exec") is not None
        aa_kernel = check_apparmor_kernel()
        aa_sudoers = is_apparmor_sudoers_configured() if aa_available else False
        info["available"] = aa_available
        info["method"] = "apparmor"  # always show method on Linux regardless of availability
        info["details"] = {
            "apparmor_kernel": aa_kernel,
            "apparmor_tools": aa_tools,
            "apparmor_sudoers": aa_sudoers,
            "aa_exec_path": shutil.which("aa-exec"),
        }
        # Setup guidance
        if not aa_available or not aa_sudoers:
            info["setup"] = build_setup_guidance(
                aa_kernel, aa_tools, aa_sudoers,
            )
    elif IS_MACOS:
        sb_available = is_sandbox_exec_available()
        info["available"] = sb_available
        info["method"] = "sandbox-exec (experimental)" if sb_available else None
        info["details"] = {
            "sandbox_exec": sb_available,
            "note": "sandbox-exec is deprecated by Apple",
        }
    elif IS_WINDOWS:
        info["available"] = True
        info["method"] = "restricted_token+job_object"
        info["details"] = {
            "restricted_token": True,
            "job_object": True,
        }

    return info
