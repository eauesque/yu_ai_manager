"""AppArmor (Linux) isolation helpers.

Provides AppArmor profile management: availability check, profile
generation, loading/unloading, and command wrapping with aa-exec.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Generated AppArmor profiles live under the app cache, never /tmp -- see
# `_private_profile_dir`.
_APPARMOR_PROFILE_DIR_NAME = "yu_ai_apparmor"
_EXTENSION_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")



def _private_profile_dir(name: str) -> Path:
    """Return an owner-only directory for generated sandbox profiles.

    NOT `/tmp`: that path is world-writable and the name is fixed, so another
    user can create it first. `mkdir(mode=0o700, exist_ok=True)` would then
    accept their directory as-is -- neither applying the mode nor checking the
    owner -- and whatever they put inside becomes the sandbox policy this
    process hands to `sandbox-exec` / `apparmor_parser`.
    """
    from core.paths import get_cache_dir

    profile_dir = get_cache_dir() / name
    profile_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    # The directory may predate this call. Verify rather than assume.
    info = profile_dir.stat()
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise PermissionError(
            f"{profile_dir} is not owned by this process; refusing to write a "
            "sandbox profile into it"
        )
    if info.st_mode & 0o077:
        # Tighten rather than fail: we own it, so this is recoverable.
        profile_dir.chmod(0o700)
    return profile_dir


def is_apparmor_available() -> bool:
    """Check whether AppArmor is enabled in the kernel and tools exist."""
    import sys
    if not sys.platform.startswith("linux"):
        return False
    # Check if kernel module is enabled
    enabled_path = "/sys/module/apparmor/parameters/enabled"
    try:
        with open(enabled_path) as f:
            if f.read().strip() != "Y":
                return False
    except OSError:
        return False
    # Check if aa-exec command exists
    return shutil.which("aa-exec") is not None


def apparmor_profile_name(ext_name: str) -> str:
    """Generate an AppArmor profile name from the extension name."""
    if not isinstance(ext_name, str) or not _EXTENSION_NAME_RE.fullmatch(ext_name):
        raise ValueError("invalid extension name for AppArmor profile")
    safe = ext_name.replace("-", "_").replace(".", "_")
    return f"yu_ai_ext_{safe}"


def generate_apparmor_profile(
    ext_name: str,
    ext_dir: Path,
    permissions: set,
    scan_roots: list[str] | None = None,
    project_root: Path | None = None,
    db_path: Path | None = None,
) -> str:
    """Generate an AppArmor profile from extension permissions."""
    from .os_isolation_profiles import build_apparmor_profile
    return build_apparmor_profile(
        profile_name=apparmor_profile_name(ext_name),
        ext_dir=ext_dir,
        permissions=permissions,
        scan_roots=scan_roots or [],
        project_root=project_root or Path(__file__).resolve().parents[3],
        db_path=db_path,
    )


def is_apparmor_sudoers_configured() -> bool:
    """Check whether NOPASSWD sudoers rule is configured for apparmor_parser.

    Attempts sudo -n (non-interactive) with apparmor_parser --help
    to determine if password-less execution is possible.
    """
    parser = shutil.which("apparmor_parser")
    if not parser:
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", parser, "--help"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def load_apparmor_profile(ext_name: str, profile_content: str) -> bool:
    """Load an AppArmor profile into the kernel.

    Uses apparmor_parser -r to overwrite-load existing profiles.
    Requires NOPASSWD sudoers configuration (via setup-apparmor.sh).
    """
    if not is_apparmor_sudoers_configured():
        logger.warning(
            f"{ext_name}: sudoers not configured, cannot load AppArmor profile. "
            "Run sudo bash scripts/setup-apparmor.sh"
        )
        return False

    profile_name = apparmor_profile_name(ext_name)
    profile_dir = _private_profile_dir(_APPARMOR_PROFILE_DIR_NAME)
    profile_path = profile_dir / profile_name

    try:
        profile_path.write_text(profile_content, encoding="utf-8")
        result = subprocess.run(
            ["sudo", "-n", "apparmor_parser", "-r", str(profile_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                f"AppArmor profile load failed ({profile_name}): "
                f"{result.stderr.strip()}"
            )
            return False
        logger.info(f"AppArmor profile loaded: {profile_name}")
        return True
    except subprocess.TimeoutExpired:
        logger.warning(f"AppArmor profile load timeout: {profile_name}")
        return False
    except FileNotFoundError:
        logger.warning("apparmor_parser not found")
        return False
    except Exception as exc:
        logger.warning(f"AppArmor profile load error: {exc}")
        return False


def unload_apparmor_profile(ext_name: str) -> bool:
    """Unload an AppArmor profile from the kernel."""
    profile_name = apparmor_profile_name(ext_name)
    profile_path = _private_profile_dir(_APPARMOR_PROFILE_DIR_NAME) / profile_name

    if not profile_path.exists():
        return True

    if not is_apparmor_sudoers_configured():
        logger.warning(f"{ext_name}: sudoers not configured, skipping unload")
        return False

    try:
        result = subprocess.run(
            ["sudo", "-n", "apparmor_parser", "-R", str(profile_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            profile_path.unlink(missing_ok=True)
            logger.info(f"AppArmor profile unloaded: {profile_name}")
        return result.returncode == 0
    except Exception as exc:
        logger.warning(f"AppArmor profile unload error: {exc}")
        return False


def build_apparmor_command(
    cmd: list[str], ext_name: str
) -> list[str]:
    """Prepend aa-exec prefix to a command."""
    profile_name = apparmor_profile_name(ext_name)
    return ["aa-exec", "-p", profile_name, "--"] + cmd


def check_apparmor_kernel() -> str:
    """Return the AppArmor kernel module status string."""
    enabled_path = "/sys/module/apparmor/parameters/enabled"
    try:
        with open(enabled_path) as f:
            val = f.read().strip()
            return "enabled" if val == "Y" else f"disabled ({val})"
    except OSError:
        return "not_found"


def build_setup_guidance(
    kernel_status: str, tools_installed: bool, sudoers_ok: bool,
) -> dict:
    """Build AppArmor setup guidance information."""
    steps: list[str] = []
    if not tools_installed:
        steps.append("sudo apt install apparmor apparmor-utils")
    if kernel_status != "enabled":
        steps.append("sudo bash scripts/setup-apparmor.sh")
        steps.append("sudo reboot")
    elif not sudoers_ok:
        steps.append("sudo bash scripts/setup-apparmor.sh")

    return {
        "required": True,
        "command": "sudo bash scripts/setup-apparmor.sh",
        "steps": steps,
        "needs_reboot": kernel_status != "enabled",
        "message": (
            "AppArmor activation requires running the setup script. "
            "Execute sudo bash scripts/setup-apparmor.sh in a terminal."
        ),
    }
