"""Environment snapshot assembly for diagnostics bundles."""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
import sys
from typing import Any

from core.search_api.server_info import build_server_info_response
from core.web.error_bundle_capture import build_error_bundle


def _tool_version(command: str) -> str | None:
    exe = shutil.which(command)
    if not exe:
        return None
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=3, check=False)
    except Exception:
        return None
    first = (result.stdout or result.stderr).splitlines()
    return first[0].strip() if first else None


async def _capture_error_bundle() -> dict[str, Any]:
    try:
        return await build_error_bundle(RuntimeError("diagnostics snapshot"))
    except Exception as exc:
        return {"capture_error": type(exc).__name__}


def _run_error_bundle_capture() -> dict[str, Any]:
    try:
        return asyncio.run(_capture_error_bundle())
    except RuntimeError:
        return {"capture_error": "event_loop_running"}


def _gpu_info() -> dict[str, Any]:
    try:
        from core.system import gpu_info  # type: ignore[attr-defined]  # noqa: PLC0415
    except Exception as exc:
        return {"available": False, "capture_error": type(exc).__name__}
    getter = getattr(gpu_info, "get_gpu_info", None)
    if not callable(getter):
        return {"available": False}
    try:
        result = getter()
    except Exception as exc:
        return {"available": False, "capture_error": type(exc).__name__}
    return result if isinstance(result, dict) else {"value": result}


def _onnxruntime_info() -> dict[str, Any]:
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:
        return {"available": False, "capture_error": type(exc).__name__}
    return {
        "available": True,
        "version": getattr(ort, "__version__", ""),
        "providers": list(ort.get_available_providers()),
    }


def build_environment_snapshot(app_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = app_config or {}
    try:
        server_info = build_server_info_response(config, session_obj=None, local_only_ok=True, host="127.0.0.1")
    except Exception as exc:
        server_info = {"capture_error": type(exc).__name__}
    error_bundle = _run_error_bundle_capture()
    runtime_obj = error_bundle.get("runtime")
    runtime = runtime_obj if isinstance(runtime_obj, dict) else {}
    state_obj = error_bundle.get("state")
    state = state_obj if isinstance(state_obj, dict) else {}
    return {
        "app": {
            "name": "YU AI Manager",
            "version": server_info.get("version"),
            "schema_version": server_info.get("schema_version"),
            "active_profile": server_info.get("active_profile"),
            "active_ui": server_info.get("active_ui") or config.get("ACTIVE_UI"),
        },
        "runtime": {
            "os": runtime.get("os") or {"platform": platform.system(), "release": platform.release(), "arch": platform.machine()},
            "platform": platform.platform(),
            "python": runtime.get("python") or sys.version.split()[0],
            "node": _tool_version("node"),
            "pnpm": _tool_version("pnpm"),
            "uv": _tool_version("uv"),
            "gpu": _gpu_info(),
            "onnxruntime": _onnxruntime_info(),
        },
        "state": {
            "server_info": server_info,
            "error_bundle": error_bundle,
            "db_path": server_info.get("db_path"),
            "last_api_endpoint": (error_bundle.get("request") or {}).get("endpoint") if isinstance(error_bundle.get("request"), dict) else None,
            "startup": state.get("db"),
        },
    }
