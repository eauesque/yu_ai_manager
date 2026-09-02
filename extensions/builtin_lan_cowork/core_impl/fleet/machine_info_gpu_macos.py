"""macOS GPU probe for fleet machine info."""

from __future__ import annotations

import platform
import subprocess


def gpu_macos() -> list[dict] | None:
    if platform.system() != "Darwin":
        return None
    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    except Exception:
        return None
    if result.returncode != 0:
        return None

    name = ""
    vram_gb: float | None = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not name and stripped.startswith("Chipset Model:"):
            name = stripped.split(":", 1)[-1].strip()
        elif vram_gb is None and stripped.startswith("VRAM"):
            parts = stripped.split(":", 1)[-1].strip().split()
            if len(parts) >= 2:
                try:
                    num = float(parts[0].replace(",", ""))
                    unit = parts[1].upper()
                    if unit.startswith("GB"):
                        vram_gb = round(num, 1)
                    elif unit.startswith("MB"):
                        vram_gb = round(num / 1024.0, 1)
                except ValueError:
                    pass
    if not name:
        return None
    return [{"name": name, "vram_total_gb": vram_gb, "vram_used_gb": None, "utilization_pct": None}]
