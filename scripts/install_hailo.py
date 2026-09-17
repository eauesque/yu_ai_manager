"""Auto-install Hailo Python runtime (hailort) from a locally staged wheel.

The Hailo Python wheel (``hailort-*-cp*-cp*-linux_*.whl``) is **not** on PyPI
and the Hailo Developer Zone does not ship an aarch64 wheel. On Pi hosts the
wheel is built once from ``~/hailort/`` and staged under the user home (most
commonly ``~/share/``). When the project venv is rebuilt by ``uv`` the wheel
is not re-installed automatically — this script restores it.

Behavior:

1. If ``hailo_platform`` already imports in the project venv → exit 0 silently.
2. Otherwise search a small set of well-known directories under ``$HOME`` for
   a ``hailort-*.whl`` matching the current Python version + machine arch.
3. If exactly one wheel is found, ``uv pip install`` it. If several are found,
   pick the newest by mtime. If none, exit 0 silently (Hailo is optional —
   Windows/macOS/x86 machines have no wheel and that is fine).

Stdlib only so this can run before ``uv sync`` finishes wiring deps.

Override the wheel path with ``HAILORT_WHEEL=/abs/path/to/wheel.whl``.

Usage:
    uv run --no-project python scripts/install_hailo.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories under $HOME that we search for a staged wheel, in priority order.
_SEARCH_DIRS = ("share", "hailort", "Downloads", "")

_WHEEL_RE = re.compile(
    r"^hailort-(?P<ver>[^-]+)-cp(?P<pymaj>\d)(?P<pymin>\d+)-cp\d+\d+-linux_(?P<arch>[a-z0-9_]+)\.whl$"
)


def _venv_python() -> Path | None:
    """Return the project venv's python, or None if the venv hasn't been built yet."""
    p = PROJECT_ROOT / ".venv" / "bin" / "python"
    return p if p.exists() else None


def _already_installed() -> bool:
    py = _venv_python()
    if py is None:
        return False
    r = subprocess.run(
        [str(py), "-c", "import hailo_platform"],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _current_py_tag() -> tuple[int, int]:
    return sys.version_info.major, sys.version_info.minor


def _current_arch() -> str:
    # platform.machine() — aarch64 on Pi, x86_64 on Intel/AMD Linux.
    import platform

    return platform.machine()


def _find_wheel() -> Path | None:
    override = os.environ.get("HAILORT_WHEEL", "").strip()
    if override:
        p = Path(override).expanduser()
        return p if p.is_file() else None

    home = Path.home()
    py_maj, py_min = _current_py_tag()
    arch = _current_arch()

    candidates: list[Path] = []
    seen: set[Path] = set()
    for sub in _SEARCH_DIRS:
        d = home / sub if sub else home
        if not d.is_dir():
            continue
        try:
            for entry in d.iterdir():
                if not entry.is_file():
                    continue
                m = _WHEEL_RE.match(entry.name)
                if not m:
                    continue
                if int(m["pymaj"]) != py_maj or int(m["pymin"]) != py_min:
                    continue
                if m["arch"] != arch:
                    continue
                if entry in seen:
                    continue
                seen.add(entry)
                candidates.append(entry)
        except PermissionError:
            continue

    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _uv_bin() -> str:
    # Prefer the project-bundled uv (bin/uv) if present, else PATH.
    bundled = PROJECT_ROOT / "bin" / "uv"
    return str(bundled) if bundled.exists() else "uv"


def main() -> int:
    if _already_installed():
        return 0

    wheel = _find_wheel()
    if wheel is None:
        # Optional dependency. Silent success keeps non-Pi launches noise-free.
        return 0

    print(f"[install_hailo] installing {wheel.name}", file=sys.stderr)
    r = subprocess.run(
        [_uv_bin(), "pip", "install", "--quiet", str(wheel)],
        cwd=PROJECT_ROOT,
    )
    if r.returncode != 0:
        print(f"[install_hailo] uv pip install failed (exit {r.returncode})", file=sys.stderr)
        return r.returncode

    if _already_installed():
        print("[install_hailo] hailo_platform ready", file=sys.stderr)
        return 0
    print("[install_hailo] install completed but hailo_platform still not importable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
