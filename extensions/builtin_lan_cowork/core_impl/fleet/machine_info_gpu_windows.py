"""Windows GPU probe for fleet machine info."""

from __future__ import annotations

import platform
import subprocess


def gpu_names_windows_wmi() -> list[str]:
    if platform.system() != "Windows":
        return []
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_VideoController).Name",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
