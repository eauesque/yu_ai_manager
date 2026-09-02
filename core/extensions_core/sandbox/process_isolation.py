"""Extension process isolation — public API and process registry.

Re-exports all public symbols from submodules for backward compatibility.
Callers can continue to ``from core.extensions_core.process_isolation import ...``.
"""

from __future__ import annotations

import logging
import sys

from .ipc_protocol import MAX_MSG_SIZE as _MAX_MSG_SIZE  # noqa: F401
from .ipc_protocol import IPCError  # noqa: F401
from .ipc_protocol import deserialize_args as _deserialize_args  # noqa: F401
from .ipc_protocol import recv_msg as _recv_msg  # noqa: F401
from .ipc_protocol import send_msg as _send_msg  # noqa: F401
from .ipc_protocol import serialize_args as _serialize_args  # noqa: F401
from .isolated_process import IsolatedExtensionProcess  # noqa: F401

logger = logging.getLogger(__name__)

# Platform check
IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Availability / policy helpers
# ---------------------------------------------------------------------------

def is_isolation_available() -> bool:
    """Return True if process isolation is available on this platform."""
    return IS_LINUX


def should_isolate(ext_name: str, config: dict) -> bool:
    """Decide whether *ext_name* should run in an isolated process."""
    if not is_isolation_available():
        return False

    iso_config = config.get("process_isolation", {})
    if not iso_config.get("enabled", False):
        return False

    # Explicit extension list
    explicit = iso_config.get("extensions", [])
    if ext_name in explicit:
        return True

    # L2 automatic isolation
    if iso_config.get("auto_l2", False):
        from core.extensions_core.extensions_defs import TrustLevel
        from core.extensions_core.lifecycle.runtime import get_extension_manager
        try:
            mgr = get_extension_manager()
            manifest = mgr.manifests.get(ext_name)
            if manifest and manifest.trust_level == TrustLevel.UNTRUSTED:
                return True
        except Exception:
            # Falling through to `return False` means NOT isolating. An
            # unreadable manifest must not quietly become "trusted enough".
            logger.warning(
                "auto-L2 isolation check for %s did not complete; not isolating",
                ext_name, exc_info=True,
            )

    return False


# ---------------------------------------------------------------------------
# Process management registry
# ---------------------------------------------------------------------------

_isolated_processes: dict[str, IsolatedExtensionProcess] = {}


def get_isolated_process(ext_name: str) -> IsolatedExtensionProcess | None:
    """Look up a running isolated process by extension name."""
    return _isolated_processes.get(ext_name)


def register_isolated_process(ext_name: str, proc: IsolatedExtensionProcess) -> None:
    """Register an isolated process in the global registry."""
    _isolated_processes[ext_name] = proc


def stop_all_isolated_processes() -> None:
    """Stop every registered isolated process."""
    for name, proc in list(_isolated_processes.items()):
        try:
            proc.stop()
        except Exception as exc:
            logger.error(f"{name}: Stop error: {exc}")
    _isolated_processes.clear()


def get_isolation_status() -> list[dict]:
    """Return status info for all isolated processes (API use)."""
    result = []
    for name, proc in _isolated_processes.items():
        entry = {
            "ext_name": name,
            "alive": proc.is_alive(),
            "pid": proc._process.pid if proc._process else None,
            "socket": proc._socket_path,
        }
        # Phase D: Include OS isolation status
        if proc._process and proc._process.poll() is None:
            env = getattr(proc, "_applied_env", {})
            if not env and proc._process:
                # Determine from environment variables (set at startup)
                pass
        result.append(entry)
    return result


def get_os_isolation_status() -> dict:
    """Return overall OS-level isolation status (API use)."""
    try:
        from core.extensions_core.sandbox.os_isolation import get_os_isolation_info
        return get_os_isolation_info()
    except Exception:
        return {"available": False, "method": None, "platform": sys.platform}
