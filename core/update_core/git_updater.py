"""Git-based self-update: fetch, pull, reinstall deps if changed."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Callable

from core.update_core.detect import PROJECT_ROOT
from core.update_core.pre_update_backup import create_pre_update_backup

logger = logging.getLogger(__name__)

# Step names in execution order
STEPS = ("backup", "fetch", "pull", "pip_install", "ts_build", "complete")


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess with sensible defaults."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=PROJECT_ROOT,
        **kwargs,
    )


def _needs_pip_install() -> bool:
    """Check if requirements.txt changed between HEAD and FETCH_HEAD."""
    try:
        result = _run(["git", "diff", "HEAD", "FETCH_HEAD", "--name-only"])
        return "requirements.txt" in (result.stdout or "")
    except Exception:
        return False


def _needs_ts_build() -> bool:
    """Check if package.json changed between HEAD and FETCH_HEAD."""
    try:
        result = _run(["git", "diff", "HEAD", "FETCH_HEAD", "--name-only"])
        return "package.json" in (result.stdout or "")
    except Exception:
        return False


def _find_command(candidates: list[str]) -> str | None:
    """Return the first command found on PATH."""
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return None


def run_git_update(emit_progress: Callable[[str, str, str], None]) -> dict:
    """Execute a full git-based update sequence.

    Args:
        emit_progress: callback(step, status, detail) to report progress.
            status is one of: "running", "success", "skipped", "error".

    Returns:
        dict with success, steps_completed, error, restart_required.
    """
    steps_completed: list[str] = []
    error: str | None = None

    # ── Step 1: backup ──
    emit_progress("backup", "running", "")
    try:
        backup_result = create_pre_update_backup()
        if backup_result["success"]:
            emit_progress("backup", "success", backup_result.get("backup_path", ""))
        else:
            # Non-fatal; continue with warning
            emit_progress("backup", "error", backup_result.get("error", "backup failed"))
        steps_completed.append("backup")
    except Exception as exc:
        emit_progress("backup", "error", str(exc))
        steps_completed.append("backup")

    # ── Step 2: fetch ──
    emit_progress("fetch", "running", "")
    try:
        result = _run(["git", "fetch", "origin"])
        if result.returncode != 0:
            error = f"git fetch failed: {result.stderr.strip()}"
            emit_progress("fetch", "error", error)
            return {"success": False, "steps_completed": steps_completed,
                    "error": error, "restart_required": False}
        emit_progress("fetch", "success", "")
        steps_completed.append("fetch")
    except subprocess.TimeoutExpired:
        error = "git fetch timed out"
        emit_progress("fetch", "error", error)
        return {"success": False, "steps_completed": steps_completed,
                "error": error, "restart_required": False}
    except Exception as exc:
        error = f"git fetch error: {exc}"
        emit_progress("fetch", "error", error)
        return {"success": False, "steps_completed": steps_completed,
                "error": error, "restart_required": False}

    # Check what files changed BEFORE pulling
    pip_needed = _needs_pip_install()
    ts_needed = _needs_ts_build()

    # ── Step 3: pull ──
    emit_progress("pull", "running", "")
    try:
        result = _run(["git", "pull", "origin", "main"])
        if result.returncode != 0:
            error = f"git pull failed: {result.stderr.strip()}"
            emit_progress("pull", "error", error)
            return {"success": False, "steps_completed": steps_completed,
                    "error": error, "restart_required": False}
        detail = result.stdout.strip().split("\n")[-1] if result.stdout else ""
        emit_progress("pull", "success", detail)
        steps_completed.append("pull")
    except subprocess.TimeoutExpired:
        error = "git pull timed out"
        emit_progress("pull", "error", error)
        return {"success": False, "steps_completed": steps_completed,
                "error": error, "restart_required": False}
    except Exception as exc:
        error = f"git pull error: {exc}"
        emit_progress("pull", "error", error)
        return {"success": False, "steps_completed": steps_completed,
                "error": error, "restart_required": False}

    # ── Step 4: pip install (conditional) ──
    if pip_needed:
        emit_progress("pip_install", "running", "")
        pip_cmd = _find_command(["uv"])
        req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
        args = ["uv", "pip", "install", "-r", req_path] if pip_cmd == "uv" else ["pip", "install", "-r", req_path]
        try:
            result = _run(args)
            if result.returncode != 0:
                error = f"pip install failed: {result.stderr.strip()}"
                emit_progress("pip_install", "error", error)
                return {"success": False, "steps_completed": steps_completed,
                        "error": error, "restart_required": True}
            emit_progress("pip_install", "success", "")
            steps_completed.append("pip_install")
        except Exception as exc:
            error = f"pip install error: {exc}"
            emit_progress("pip_install", "error", error)
            return {"success": False, "steps_completed": steps_completed,
                    "error": error, "restart_required": True}
    else:
        emit_progress("pip_install", "skipped", "requirements.txt unchanged")
        steps_completed.append("pip_install")

    # ── Step 5: TypeScript build (conditional) ──
    if ts_needed:
        emit_progress("ts_build", "running", "")
        ts_cmd = _find_command(["pnpm", "npm"])
        if ts_cmd:
            args = [ts_cmd, "run", "build"]
        else:
            emit_progress("ts_build", "skipped", "no pnpm/npm found")
            steps_completed.append("ts_build")
            ts_cmd = None
        if ts_cmd:
            try:
                result = _run(args)
                if result.returncode != 0:
                    # TS build failure is non-fatal for server operation
                    emit_progress("ts_build", "error", result.stderr.strip()[:200])
                    logger.warning("TS build failed but continuing: %s", result.stderr[:200])
                else:
                    emit_progress("ts_build", "success", "")
                steps_completed.append("ts_build")
            except Exception as exc:
                emit_progress("ts_build", "error", str(exc))
                steps_completed.append("ts_build")
    else:
        emit_progress("ts_build", "skipped", "package.json unchanged")
        steps_completed.append("ts_build")

    # ── Complete ──
    emit_progress("complete", "success", "")
    steps_completed.append("complete")

    return {
        "success": True,
        "steps_completed": steps_completed,
        "error": None,
        "restart_required": True,
    }
