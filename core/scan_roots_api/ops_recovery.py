"""One-time scan_roots recovery.

Detects and offers to restore scan roots lost to the stale-read /
reorder-overwrite bug fixed in v4.681.6 (a write action could overwrite
config.json's ``scan_roots`` with a stale, possibly empty, in-memory
snapshot). See ``core/schema_core/schema_migrate_steps_88.py`` for the
migration that plants the marker this module reads.
"""

import json
import logging
import re
from typing import Any

from core.configuration.api import load_config_json
from core.paths import data_path

logger = logging.getLogger(__name__)

_MARKER_NAME = "scan_roots_recovery_pending.json"

# Directory names that must never be auto-registered as a scan root when
# they appear one level below a drive letter -- e.g. "C:\Users" (every
# profile on the machine, not just the library owner's) or "C:\Windows".
# The orphan-root reconstruction in scanned_roots_payload() deliberately
# falls back to a coarse 1-2-segment bucket when it cannot merge a path
# into something more specific (see core/debug_api/roots_ops.py's
# _extract_root_dir), which is fine for the informational "スキャン済み
# ルート" summary a human reads, but not for a path this feature can
# register with one click.
_DANGEROUS_ROOT_NAMES = frozenset(
    {
        "users",
        "windows",
        "program files",
        "program files (x86)",
        "programdata",
        "system volume information",
        "$recycle.bin",
        "appdata",
        "boot",
        "recovery",
        "perflogs",
    }
)

_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:\\?$")
_DRIVE_SHARE_RE = re.compile(r"^[A-Za-z]\$$")
# Special administrative UNC shares with no ordinary-data-folder meaning of
# their own -- ADMIN$ *is* the Windows install directory (an alias for
# "\\<host>\<systemdrive>\Windows", not a drive letter share), IPC$ is a
# named pipe (not a filesystem path at all), and NETLOGON/SYSVOL/PRINT$ are
# Windows domain-controller/print-spooler shares. None of these are ever a
# reasonable media-library scan root.
_DANGEROUS_UNC_SHARE_NAMES = frozenset(
    {"admin$", "ipc$", "print$", "netlogon", "sysvol"}
)


def _strip_verbatim_prefix(path: str) -> str:
    """Undo Windows' "verbatim"/device-namespace path prefixes.

    ``\\\\?\\C:\\Users``, ``\\\\?\\UNC\\host\\share``, ``\\\\.\\C:\\Users``,
    and ``\\\\.\\UNC\\host\\share`` are all the same locations as
    ``C:\\Users`` and ``\\\\host\\share`` -- just spelled so the length
    limit and ``.``/``..`` normalization are skipped (``\\\\?\\...``, what
    ``std::fs::canonicalize`` emits on Windows) or so the path resolves
    through the Win32 device namespace instead of the NT object manager
    (``\\\\.\\...``); both namespaces alias UNC the same way, via a
    ``UNC\\`` sub-prefix rather than a drive letter. Segment-counting any
    of these spellings directly undercounts by the prefix's own
    segment(s) and lets a disguised ``C:\\Users`` (or bare UNC share)
    slip past the broad-root check.
    """
    for prefix in ("\\\\?\\", "\\\\.\\"):
        if path[: len(prefix)] != prefix:
            continue
        rest = path[len(prefix) :]
        if rest[:4].upper() == "UNC\\":
            return "\\\\" + rest[4:]
        return rest
    return path


def _is_dangerously_broad(path: str) -> bool:
    """Would registering `path` as a recursive scan root be reckless?

    Rejects bare drive roots ("C:", "C:\\") and well-known shallow system
    directories ("C:\\Users", "C:\\Windows", ...) regardless of drive
    letter -- a data drive mounted with one of these names is exotic
    enough that refusing it too is the safe default. A bare UNC share
    ("\\\\host\\share", no subpath) is rejected the same way a bare drive
    letter is: for UNC, host+share together are the volume, so a subpath
    is one segment deeper than for a local drive.

    Windows administrative shares are aliases for exactly these same
    dangerous locations and are unwound before the check above ever sees
    them: ``\\\\host\\C$\\...`` *is* ``C:\\...`` on that host (share names
    of the form ``<drive>$`` map straight to the drive's root, remote host
    or not), and ``\\\\host\\ADMIN$``/``IPC$``/``PRINT$``/``NETLOGON``/
    ``SYSVOL`` name Windows-internal shares with no ordinary-data-folder
    meaning at all -- rejected outright regardless of what follows them.
    """
    raw = _strip_verbatim_prefix(path.strip())
    p = raw.rstrip("\\/")
    if not p:
        return True
    if _DRIVE_ROOT_RE.fullmatch(p + ("\\" if not p.endswith(":") else "")):
        return True
    is_unc = raw.startswith("\\\\") or raw.startswith("//")
    parts = [seg for seg in re.split(r"[\\/]+", p) if seg]
    if is_unc and len(parts) >= 2:
        share = parts[1].strip().lower()
        if share in _DANGEROUS_UNC_SHARE_NAMES:
            return True
        if _DRIVE_SHARE_RE.fullmatch(parts[1].strip()):
            # "\\host\C$\rest..." aliases "C:\rest...": re-run the local
            # -path rule against the drive it actually points at.
            return _is_dangerously_broad(parts[1][0] + ":\\" + "\\".join(parts[2:]))
    min_depth = 3 if is_unc else 2
    if len(parts) < min_depth:
        return True
    if not is_unc and len(parts) == 2:
        return parts[1].strip().lower() in _DANGEROUS_ROOT_NAMES
    return False


def _filter_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = []
    for c in candidates:
        path = c.get("path")
        if isinstance(path, str) and not _is_dangerously_broad(path):
            kept.append(c)
        elif isinstance(path, str):
            logger.warning(
                "scan_roots recovery: refusing dangerously broad candidate %r", path
            )
    return kept


def _marker_path():
    return data_path(_MARKER_NAME)


def _read_marker() -> dict:
    try:
        return json.loads(_marker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_marker(pending: bool) -> None:
    try:
        _marker_path().write_text(json.dumps({"pending": pending}), encoding="utf-8")
    except OSError:
        logger.warning("Failed to write scan_roots recovery marker", exc_info=True)


def recovery_check() -> tuple[dict[str, Any], int]:
    """Is a recovery banner still warranted, and if so, with which candidates?

    The heavy candidate computation (a full ``files`` table scan, via
    ``scanned_roots_payload``) only runs when the marker is present and
    ``scan_roots`` is still empty -- unaffected installs never pay for it.
    """
    if not _marker_path().exists():
        return {"pending": False}, 200
    if not _read_marker().get("pending", True):
        return {"pending": False}, 200

    config = load_config_json(None)
    if config.get("scan_roots"):
        # Resolved by other means (manual add, an earlier apply) -- stop asking.
        _write_marker(False)
        return {"pending": False}, 200

    from core.debug_api.roots_ops import scanned_roots_payload

    payload, status = scanned_roots_payload()
    if status != 200:
        return {"pending": False}, 200
    candidates = _filter_candidates(payload.get("roots", []))
    if not candidates:
        _write_marker(False)
        return {"pending": False}, 200
    return {"pending": True, "candidates": candidates}, 200


def recovery_apply(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Register the chosen candidates as scan roots.

    Candidates are recomputed server-side and used as an allowlist --
    ``data["paths"]`` (if given) only narrows that set, it never injects an
    arbitrary path the scan did not itself surface.
    """
    from core.debug_api.roots_ops import scanned_roots_payload
    from core.scan_roots_api.ops_write import add_scan_root

    payload, status = scanned_roots_payload()
    if status != 200:
        return {
            "error": "Failed to compute recovery candidates",
            "code": "recovery_unavailable",
        }, 500
    candidate_paths = {
        c["path"] for c in _filter_candidates(payload.get("roots", [])) if c.get("path")
    }

    requested = data.get("paths")
    if requested is not None:
        if not isinstance(requested, list):
            return {"error": "paths must be a list", "code": "invalid_paths"}, 400
        selected = [p for p in requested if isinstance(p, str) and p in candidate_paths]
    else:
        selected = sorted(candidate_paths)

    added: list[dict[str, Any]] = []
    skipped: list[str] = []
    for path in selected:
        new_root, err = add_scan_root(
            {
                "path": path,
                "recursive": True,
                "enabled": True,
                "comment": "auto-recovered (v4.681.6)",
            }
        )
        if err:
            skipped.append(path)
        else:
            added.append(new_root)

    _write_marker(False)
    return {"added": added, "skipped": skipped}, 200


def recovery_dismiss() -> tuple[dict[str, Any], int]:
    _write_marker(False)
    return {"ok": True}, 200
