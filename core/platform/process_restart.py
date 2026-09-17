"""OS-specific process restart.

Windows / macOS: subprocess.Popen + os._exit (new independent process)
Linux:           os.closerange + os.execv (process replacement)

macOS shares the Windows path because os.closerange() can trip
libdispatch / CoreFoundation into abort()ing the process before execv
runs — no Python traceback, just a SIGKILL'd shell. Using Popen + _exit
avoids touching low fds entirely; Hypercorn's SO_REUSEADDR lets the new
process rebind the listen port immediately on Unix.
"""

import contextlib
import os
import subprocess

from .detect import is_macos, is_windows


def exec_restart(exec_args: list) -> None:
    """Restart the server. The process terminates or is replaced after this call."""
    if is_windows():
        subprocess.Popen(
            exec_args,
            close_fds=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        os._exit(0)
    elif is_macos():
        # Detach into a new session so the child survives the parent's exit
        # and doesn't get SIGHUP'd when the old process terminates.
        subprocess.Popen(
            exec_args,
            close_fds=True,
            start_new_session=True,
        )
        os._exit(0)
    else:
        try:
            max_fd = os.sysconf("SC_OPEN_MAX")
        except Exception:
            max_fd = 4096
        with contextlib.suppress(Exception):
            os.closerange(3, int(max_fd))
        os.execv(exec_args[0], exec_args)
