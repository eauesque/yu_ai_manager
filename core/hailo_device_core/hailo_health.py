"""Shared Hailo health building blocks used by builtin_hailo_* extensions.

Each extension layers its own HEF presence check on top of the base
{runtime_ok, hardware_ok} probe and returns the unified shape consumed by
the extension health API (see ``core.extensions_core.lifecycle.extensions_health``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _runtime_ok() -> bool:
    try:
        import hailo_platform  # noqa: F401
        return True
    except ImportError:
        return False


def _hardware_ok() -> bool:
    """Whether at least one Hailo device node exists under /dev.

    Note: this is a node-presence check (kernel module loaded + device
    enumerated), not a usability check. A device that is held exclusively
    by another process, in firmware error, or otherwise unresponsive will
    still pass this probe — the actual VDevice acquisition error will
    surface from inference paths, not here. We accept this trade-off
    because a real usability probe would require opening the device and
    risk side effects under the 500ms timeout budget.
    """
    try:
        from core.hailo_device_core.device_manager_state import list_device_paths
        return len(list_device_paths()) > 0
    except Exception:
        return False


def base_checks() -> tuple[bool, bool]:
    return _runtime_ok(), _hardware_ok()


def build_health(
    *,
    hef_ok: bool,
    hef_label: str,
    hef_hint: str = "",
) -> dict[str, Any]:
    """Compose the unified health dict for a single Hailo extension.

    The first failing check drives ``reason`` / ``reason_i18n_key`` so the UI
    can render an actionable message rather than a generic "N/A".
    """
    runtime_ok, hardware_ok = base_checks()

    if not runtime_ok:
        reason = "hailo_platform Python wheel not installed"
        key = "hailo.reason.runtime_missing"
    elif not hardware_ok:
        reason = "Hailo device /dev/hailo1x-* not found (kernel module not loaded)"
        key = "hailo.reason.device_missing"
    elif not hef_ok:
        reason = f"{hef_label} HEF not found" + (f" ({hef_hint})" if hef_hint else "")
        key = "hailo.reason.hef_missing"
    else:
        reason = ""
        key = ""

    return {
        "available": runtime_ok and hardware_ok and hef_ok,
        "checks": {
            "runtime_ok": runtime_ok,
            "hardware_ok": hardware_ok,
            "hef_ok": hef_ok,
        },
        "reason": reason,
        "reason_i18n_key": key,
    }


def hef_dir_has_any(hef_dir: Path, suffixes: tuple[str, ...] = (".hef",)) -> bool:
    """True when *hef_dir* contains at least one file with one of *suffixes*."""
    if not hef_dir.is_dir():
        return False
    return any(entry.is_file() and entry.suffix in suffixes for entry in hef_dir.iterdir())
