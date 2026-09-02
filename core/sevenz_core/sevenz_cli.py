"""7z CLI wrapper — replaces py7zr (LGPL) with subprocess calls to 7z.

Looks for ``7z``, ``7za``, or ``7zz`` in PATH.
All functions degrade gracefully when the CLI is not available.
"""

import contextlib
import datetime as _dt
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── CLI detection ────────────────────────────────────────────

_cli_path: str | None = None
_cli_checked = False


def _find_cli() -> str | None:
    global _cli_path, _cli_checked
    if _cli_checked:
        return _cli_path
    for name in ("7z", "7za", "7zz"):
        p = shutil.which(name)
        if p:
            _cli_path = p
            break
    _cli_checked = True
    if _cli_path:
        logger.debug("7z CLI found: %s", _cli_path)
    else:
        logger.debug("7z CLI not found in PATH")
    return _cli_path


def sevenz_available() -> bool:
    """Return True if a 7z CLI binary is available."""
    return _find_cli() is not None


def _run(args: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    """Run 7z CLI and return result. Raises on missing CLI."""
    cli = _find_cli()
    if not cli:
        raise ImportError("7z CLI is required for 7z support (install 7-Zip)")
    cmd = [cli] + args
    # CREATE_NO_WINDOW on Windows to avoid console flash
    kwargs: dict = {
        "capture_output": True,
        "timeout": timeout,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(cmd, **kwargs)


# ── Data types ───────────────────────────────────────────────

@dataclass
class SevenzEntry:
    filename: str
    size: int = 0
    modified: _dt.datetime | None = None
    is_directory: bool = False


# ── Listing ──────────────────────────────────────────────────

def list_entries(archive_path: str, timeout: float = 60) -> list[SevenzEntry]:
    """List all entries in a 7z archive using ``7z l -slt``."""
    result = _run(["l", "-slt", "--", archive_path], timeout=timeout)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"7z list failed: {stderr[:200]}")
    return _parse_slt_output(result.stdout.decode("utf-8", errors="replace"))


def _parse_slt_output(output: str) -> list[SevenzEntry]:
    """Parse ``7z l -slt`` output into entry list."""
    entries: list[SevenzEntry] = []
    current: dict = {}

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            if current.get("Path"):
                entries.append(_build_entry(current))
            current = {}
            continue
        if " = " in line:
            key, _, value = line.partition(" = ")
            current[key.strip()] = value.strip()

    # Last entry
    if current.get("Path"):
        entries.append(_build_entry(current))

    return entries


def _build_entry(d: dict) -> SevenzEntry:
    filename = d.get("Path", "")
    size = 0
    with contextlib.suppress(ValueError, TypeError):
        size = int(d.get("Size", 0))

    modified = None
    mod_str = d.get("Modified", "")
    if mod_str:
        with contextlib.suppress(ValueError, IndexError):
            # Naive on purpose: 7-Zip prints `Modified` in local time with
            # no zone, and the consumers call `.timestamp()`, which reads a
            # naive value as local. Attaching UTC would shift every archive
            # member's stored mtime by the UTC offset.
            modified = _dt.datetime.strptime(  # noqa: DTZ007
                mod_str[:19], "%Y-%m-%d %H:%M:%S"
            )

    is_dir = d.get("Folder", "") == "+"
    return SevenzEntry(
        filename=filename, size=size, modified=modified, is_directory=is_dir,
    )


def list_names(archive_path: str, timeout: float = 60) -> list[str]:
    """Return just the filenames in the archive."""
    return [e.filename for e in list_entries(archive_path, timeout) if not e.is_directory]


# ── Extraction ───────────────────────────────────────────────

def extract_to_dir(
    archive_path: str,
    output_dir: str,
    targets: list[str] | None = None,
    timeout: float = 120,
    max_size: int = 0,
) -> None:
    """Extract entries from 7z to output_dir.

    If *targets* is None, extracts everything.
    Uses ``-spf`` to preserve full paths.
    """
    if max_size and any(entry.size > max_size for entry in list_entries(archive_path, timeout=timeout) if not entry.is_directory and (targets is None or entry.filename in targets)):
        raise ValueError(f"7z extraction exceeds {max_size} byte limit")
    args = ["x", "-y", f"-o{output_dir}", "--", archive_path]
    if targets:
        args = ["x", "-y", f"-o{output_dir}", "--", archive_path] + targets
    result = _run(args, timeout=timeout)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"7z extract failed: {stderr[:300]}")


def read_entry_bytes(
    archive_path: str, internal_path: str,
    max_size: int = 0,
    timeout: float = 60,
) -> bytes:
    """Extract a single entry and return its bytes."""
    if max_size:
        # Check size first
        for entry in list_entries(archive_path, timeout=timeout):
            if entry.filename == internal_path and entry.size > max_size:
                raise ValueError(
                    f"Entry too large: {internal_path} "
                    f"({entry.size / 1024 / 1024:.0f} MB > "
                    f"{max_size / 1024 / 1024:.0f} MB limit)"
                )

    with tempfile.TemporaryDirectory() as tmpdir:
        extract_to_dir(archive_path, tmpdir, targets=[internal_path], timeout=timeout)
        extracted = os.path.join(tmpdir, internal_path.replace("/", os.sep))
        # Path traversal prevention: ensure extracted path stays inside tmpdir
        real_extracted = os.path.realpath(extracted)
        real_tmpdir = os.path.realpath(tmpdir)
        if (
            not real_extracted.startswith(real_tmpdir + os.sep)
            and real_extracted != real_tmpdir
        ):
            raise ValueError(
                f"Path traversal detected in 7z entry: {internal_path!r}"
            )
        if not os.path.exists(real_extracted):
            raise KeyError(f"Failed to extract entry: {internal_path!r}")
        with open(real_extracted, "rb") as f:
            return f.read()


# ── Info queries ─────────────────────────────────────────────

def get_entry_info(
    archive_path: str, internal_path: str,
) -> tuple[int, int]:
    """Return (mtime_unix, size) for a single entry."""
    try:
        for entry in list_entries(archive_path):
            if entry.filename == internal_path:
                mtime = int(entry.modified.timestamp()) if entry.modified else int(os.path.getmtime(archive_path))
                return mtime, entry.size
    except Exception:
        logger.debug("7z entry step failed", exc_info=True)
    return int(os.path.getmtime(archive_path)), 0


def batch_entry_info(
    archive_path: str, internal_paths: list[str],
) -> dict[str, tuple[int, int]]:
    """Get (mtime, size) for multiple entries in a single listing."""
    result: dict[str, tuple[int, int]] = {}
    fallback_mtime = int(os.path.getmtime(archive_path)) if os.path.exists(archive_path) else 0
    try:
        entry_map = {e.filename: e for e in list_entries(archive_path)}
        for ip in internal_paths:
            entry = entry_map.get(ip)
            if entry:
                mtime = int(entry.modified.timestamp()) if entry.modified else fallback_mtime
                result[ip] = (mtime, entry.size)
            else:
                result[ip] = (fallback_mtime, 0)
    except Exception:
        for ip in internal_paths:
            if ip not in result:
                result[ip] = (fallback_mtime, 0)
    return result


# ── Password check ───────────────────────────────────────────

def needs_password(archive_path: str) -> bool:
    """Check if archive is password-protected by attempting a test."""
    try:
        result = _run(["t", "-p", "--", archive_path], timeout=10)
        stderr = result.stderr.decode("utf-8", errors="replace")
        # 7z returns non-zero and mentions "password" or "Wrong password"
        if result.returncode != 0 and ("password" in stderr.lower() or "encrypted" in stderr.lower()):
            return True
    except Exception:
        logger.debug("7z entry step failed", exc_info=True)
    return False
