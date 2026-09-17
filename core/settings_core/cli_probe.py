"""CLI discovery that also sees Windows App Execution Aliases.

`shutil.which` checks each candidate with `os.stat`. Windows App Execution
Aliases -- `%LOCALAPPDATA%\\Microsoft\\WindowsApps\\op.exe` and friends, created
by winget/Store installs -- are APPEXECLINK reparse points that `os.stat`
cannot open, so `which` reports the program as missing even though
`subprocess` launches it fine (`CreateProcess` resolves the alias). `where op`
can miss them for the same reason. `os.lstat` reads the link itself and
succeeds, so it is what we probe with.

Mirrors `executable_on_path` in crates/yu-server/src/routes/settings.rs.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys


def executable_on_path(program: str) -> bool:
    """Return True when `program` can be launched by subprocess."""
    if shutil.which(program) is not None:
        return True
    if sys.platform != "win32":
        return False
    return any(
        _is_program_file(os.path.join(directory, program + ext))
        for directory in _search_dirs()
        for ext in _path_extensions()
    )


def _search_dirs() -> list[str]:
    """PATH entries plus the fixed App Execution Alias directory."""
    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        dirs.append(os.path.join(local_appdata, "Microsoft", "WindowsApps"))
    return dirs


def _path_extensions() -> list[str]:
    """%PATHEXT% suffixes, so `bw.cmd` (npm shim) and `op.exe` both resolve."""
    raw = os.environ.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD"
    return ["", *(ext for ext in raw.split(os.pathsep) if ext)]


def _is_program_file(path: str) -> bool:
    try:
        return not stat.S_ISDIR(os.lstat(path).st_mode)
    except (OSError, ValueError):
        return False
