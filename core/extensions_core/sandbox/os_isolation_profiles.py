"""OS isolation profile generation (Phase D).

Auto-generates AppArmor (Linux) and Seatbelt (macOS, experimental)
profiles from extension permissions.
"""

from __future__ import annotations

import textwrap
from pathlib import Path


def _apparmor_path(path: str | Path, suffix: str = "") -> str:
    """Return a quoted AppArmor path rule operand, rejecting policy syntax."""
    value = str(path)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("unsafe AppArmor path")
    if any(char in value for char in "*?[]{}^,"):
        raise ValueError("unsafe AppArmor path")
    return '"' + (value + suffix).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _apparmor_profile_name(profile_name: str) -> str:
    if not isinstance(profile_name, str) or not profile_name.startswith("yu_ai_ext_"):
        raise ValueError("invalid AppArmor profile name")
    suffix = profile_name.removeprefix("yu_ai_ext_")
    if not suffix or not all(char.isascii() and (char.isalnum() or char == "_") for char in suffix):
        raise ValueError("invalid AppArmor profile name")
    return profile_name


def build_apparmor_profile(
    profile_name: str,
    ext_dir: Path,
    permissions: set,
    scan_roots: list[str],
    project_root: Path,
    db_path: Path | None = None,
) -> str:
    """Generate an AppArmor profile from extension permissions.

    Args:
        profile_name: Profile name (yu_ai_ext_xxx)
        ext_dir: Extension directory
        permissions: Set of granted permissions
        scan_roots: List of scan root paths
        project_root: Project root (yu_ai_manager/)

    Returns:
        AppArmor profile string
    """
    profile_name = _apparmor_profile_name(profile_name)
    rules: list[str] = []

    # Basic: allow Python interpreter execution
    rules.append("  # Python interpreter")
    rules.append("  /usr/bin/python3* ix,")
    rules.append("  /usr/lib/python3/** r,")
    rules.append("  /usr/lib/python3*/** r,")

    # Shared library read access (Python C extensions, etc.)
    rules.append("")
    rules.append("  # Shared libraries")
    rules.append("  /lib/** r,")
    rules.append("  /usr/lib/** r,")
    rules.append("  /usr/local/lib/** r,")

    # Minimal access to proc / sys / dev
    rules.append("")
    rules.append("  # proc/sys/dev minimal")
    rules.append("  /proc/self/** r,")
    rules.append("  /dev/null rw,")
    rules.append("  /dev/urandom r,")
    rules.append("  /tmp/** rw,")

    # Own directory: always allow read/write
    ext_path = str(ext_dir.resolve())
    rules.append("")
    rules.append("  # Extension own directory")
    rules.append(f"  owner {_apparmor_path(ext_path, '/**')} rw,")
    rules.append(f"  owner {_apparmor_path(ext_path, '/')} r,")

    # Worker runtime. Project services remain inaccessible; DB access is brokered.
    sandbox_path = str((project_root / "core" / "extensions_core" / "sandbox").resolve())
    rules.append("")
    rules.append("  # Isolated worker runtime")
    rules.append(f"  {_apparmor_path(sandbox_path, '/**')} r,")

    # Direct database access is always denied; the parent brokers read-only queries.
    data_path = str((project_root / "data").resolve())
    rules.append("")
    rules.append("  # Parent-brokered DB only")
    rules.append(f"  deny {_apparmor_path(data_path, '/**')} rw,")
    if db_path is not None:
        resolved_db = str(db_path.resolve())
        rules.append(f"  deny {_apparmor_path(resolved_db)} rw,")
        rules.append(f"  deny {_apparmor_path(resolved_db + '-wal')} rw,")
        rules.append(f"  deny {_apparmor_path(resolved_db + '-shm')} rw,")

    # Scan roots: controlled by fs permissions
    if scan_roots and _has_any_fs_permission(permissions):
        rules.append("")
        rules.append("  # Scan roots")
        for root in scan_roots:
            root_path = str(Path(root).resolve())
            if _has_permission(permissions, "fs:write:scan_roots") or \
               _has_permission(permissions, "fs:write:any"):
                rules.append(f"  {_apparmor_path(root_path, '/**')} rw,")
            elif _has_permission(permissions, "fs:read:scan_roots") or \
                 _has_permission(permissions, "fs:read:any"):
                rules.append(f"  {_apparmor_path(root_path, '/**')} r,")

    # fs:read:any / fs:write:any grants broad access
    if _has_permission(permissions, "fs:write:any"):
        rules.append("")
        rules.append("  # All file write (fs:write:any)")
        rules.append("  /** rw,")
    elif _has_permission(permissions, "fs:read:any"):
        rules.append("")
        rules.append("  # All file read (fs:read:any)")
        rules.append("  /** r,")

    # Network: controlled by permissions
    rules.append("")
    if _has_permission(permissions, "network:internet"):
        rules.append("  # Network (internet)")
        rules.append("  network tcp,")
        rules.append("  network udp,")
        rules.append("  network unix,")
    elif _has_permission(permissions, "network:local"):
        rules.append("  # Network (local only)")
        rules.append("  network tcp,")
        rules.append("  network unix,")
    else:
        rules.append("  # Network (Unix socket only = for IPC)")
        rules.append("  network unix,")
        rules.append("  deny network tcp,")
        rules.append("  deny network udp,")

    # subprocess permission
    rules.append("")
    if _has_permission(permissions, "subprocess"):
        rules.append("  # External command execution (subprocess allowed)")
        rules.append("  /usr/bin/** rix,")
        rules.append("  /bin/** rix,")
        rules.append("  /usr/local/bin/** rix,")
    else:
        rules.append("  # Deny external command execution")
        rules.append("  deny /usr/bin/** x,")
        rules.append("  deny /bin/** x,")
        rules.append("  deny /usr/sbin/** x,")
        rules.append("  deny /sbin/** x,")
        rules.append("  deny /usr/local/bin/** x,")

    rules_str = "\n".join(rules)
    return textwrap.dedent(f"""\
        #include <tunables/global>

        profile {profile_name} flags=(attach_disconnected) {{
          #include <abstractions/base>

        {rules_str}
        }}
    """)


def build_seatbelt_profile(
    ext_name: str,
    ext_dir: Path,
    permissions: set,
) -> str:
    """Generate a macOS Seatbelt (sandbox-exec) profile.

    Note: sandbox-exec is deprecated by Apple. Provided as an experimental feature.

    Args:
        ext_name: Extension name
        ext_dir: Extension directory
        permissions: Set of granted permissions

    Returns:
        Seatbelt profile string (.sb format)
    """
    rules: list[str] = []
    rules.append("(version 1)")
    rules.append("(deny default)")
    rules.append("")

    # Basic permissions
    rules.append("; 基本操作")
    rules.append("(allow process-exec)")
    rules.append("(allow process-fork)")
    rules.append("(allow signal (target self))")
    rules.append("(allow sysctl-read)")
    rules.append("")

    # File access
    rules.append("; Extension 自ディレクトリ")
    ext_path = str(ext_dir.resolve())
    rules.append(f'(allow file-read* (subpath "{ext_path}"))')
    rules.append(f'(allow file-write* (subpath "{ext_path}"))')
    rules.append("")

    # Python runtime
    rules.append("; Python ランタイム")
    rules.append('(allow file-read* (subpath "/usr/lib/python3"))')
    rules.append('(allow file-read* (subpath "/usr/local/lib/python3"))')
    rules.append('(allow file-read* (subpath "/Library/Frameworks/Python.framework"))')
    rules.append('(allow file-read* (subpath "/tmp"))')
    rules.append('(allow file-write* (subpath "/tmp"))')
    rules.append("")

    # Network
    if _has_permission(permissions, "network:internet"):
        rules.append("; ネットワーク (internet)")
        rules.append("(allow network*)")
    elif _has_permission(permissions, "network:local"):
        rules.append("; ネットワーク (local)")
        rules.append("(allow network-bind)")
        rules.append("(allow network-inbound)")
        rules.append("(allow network-outbound (to local))")
        rules.append('(allow network* (local unix-socket))')
    else:
        rules.append("; ネットワーク (Unix socket のみ)")
        rules.append('(allow network* (local unix-socket))')

    return "\n".join(rules) + "\n"


def _has_permission(permissions: set, perm: str) -> bool:
    """Check whether the permission set contains the specified permission."""
    return perm in permissions


def _has_any_fs_permission(permissions: set) -> bool:
    """Check whether any FS-related permissions are present."""
    fs_perms = {
        "fs:read:own", "fs:write:own",
        "fs:read:scan_roots", "fs:write:scan_roots",
        "fs:read:any", "fs:write:any",
    }
    return bool(permissions & fs_perms)
