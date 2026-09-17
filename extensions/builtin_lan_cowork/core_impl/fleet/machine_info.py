"""Fleet machine info collector."""

from __future__ import annotations

import datetime
import platform
import subprocess
import time

from .machine_info_gpu_linux import gpu_nvidia_smi, gpu_rocm_smi
from .machine_info_gpu_macos import gpu_macos
from .machine_info_gpu_windows import gpu_names_windows_wmi

_PROCESS_START: float = time.time()


def _git_info(repo_path: str = ".") -> dict:
    def _run(cmd: list[str]) -> str:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=5).strip()

    try:
        branch = _run(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"])
        commit = _run(["git", "-C", repo_path, "rev-parse", "--short", "HEAD"])
        dirty_out = _run(["git", "-C", repo_path, "status", "--porcelain", "--untracked-files=no"])
        return {"branch": branch, "commit": commit, "dirty": bool(dirty_out)}
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
        return {"branch": None, "commit": None, "dirty": None}
    except Exception:
        return {"branch": None, "commit": None, "dirty": None}


def _cpu_name() -> str:
    try:
        import cpuinfo  # type: ignore

        return cpuinfo.get_cpu_info().get("brand_raw", "")
    except Exception:
        try:
            return platform.processor() or ""
        except Exception:
            return ""


def _gpu_info() -> list[dict]:
    for probe in (gpu_nvidia_smi, gpu_rocm_smi, gpu_macos):
        data = probe()
        if data is not None:
            return data
    names = gpu_names_windows_wmi()
    if names:
        return [{"name": name, "vram_total_gb": None, "vram_used_gb": None, "utilization_pct": None} for name in names]
    return [{"name": "", "vram_total_gb": None, "vram_used_gb": None, "utilization_pct": None}]


def collect(version: str, roles: list, repo_path: str = ".", gpu_name: str = "") -> dict:
    import psutil

    uname = platform.uname()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(repo_path)
    gpus = _gpu_info()
    if gpu_name and gpus:
        gpus[0]["name"] = gpu_name

    return {
        "version": version,
        "os": {
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
        },
        "cpu": {
            "name": _cpu_name(),
            "cores_physical": psutil.cpu_count(logical=False) or 0,
            "cores_logical": psutil.cpu_count(logical=True) or 0,
            "usage_pct": psutil.cpu_percent(interval=0.1),
        },
        "ram": {
            "total_gb": round(ram.total / 1e9, 1),
            "used_gb": round(ram.used / 1e9, 1),
            "pct": round(ram.percent, 1),
        },
        "gpu": gpus[0],
        "gpus": gpus,
        "disk": {
            "path": str(repo_path),
            "total_gb": round(disk.total / 1e9, 1),
            "used_gb": round(disk.used / 1e9, 1),
            "pct": round(disk.percent, 1),
        },
        "process_uptime_sec": int(time.time() - _PROCESS_START),
        "git": _git_info(repo_path),
        "roles": list(roles),
        "collected_at": datetime.datetime.now().astimezone().isoformat(),
    }
