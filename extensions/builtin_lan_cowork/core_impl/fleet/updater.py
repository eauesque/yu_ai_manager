"""Fleet updater — git pull + graceful restart job."""
from __future__ import annotations

import datetime
import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class UpdateStatus:
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RESTARTING = "restarting"


def _run_git(cmd: list, repo_path: str) -> tuple[int, str, str]:
    """Run a git command; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, cwd=repo_path, capture_output=True, text=True, timeout=120
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _step(name: str, status: str, output: str = "") -> dict:
    return {"name": name, "status": status, "output": output}


async def run_update_job(
    job_id: str,
    source: str,
    branch: str,
    repo_path: str,
    local_peer_id: str,
    allowed_branches: list | None = None,
    allowed_local_sources: list | None = None,
    skip_restart: bool = False,
    data_dir: str | None = None,
) -> dict:
    """Execute a full update job. Returns final job status dict."""
    if allowed_branches is None:
        allowed_branches = ["main"]
    if allowed_local_sources is None:
        allowed_local_sources = []

    steps = []
    started_at = datetime.datetime.now().astimezone().isoformat()

    def fail(error_code: str, step_name: str, msg: str = "") -> dict:
        steps.append(_step(step_name, UpdateStatus.FAILED, error_code + (f": {msg}" if msg else "")))
        return {
            "job_id": job_id,
            "status": UpdateStatus.FAILED,
            "started_at": started_at,
            "finished_at": datetime.datetime.now().astimezone().isoformat(),
            "steps": steps,
            "error": error_code,
        }

    # Validate branch
    if branch not in allowed_branches:
        return fail("branch_not_allowed", "git_precheck", f"branch={branch}")

    # Validate source
    if source == "origin":
        remote = "origin"
    elif source.startswith("local:"):
        path_str = source[len("local:"):]
        resolved = str(Path(path_str).resolve())
        allowed_resolved = [str(Path(p).resolve()) for p in allowed_local_sources]
        if resolved not in allowed_resolved:
            return fail("local_path_not_allowed", "git_precheck", resolved)
        remote = resolved
    else:
        return fail("invalid_source", "git_precheck", source)

    # Step: git_precheck
    try:
        rc, out, err = _run_git(["git", "--version"], repo_path)
    except (FileNotFoundError, OSError):
        return fail("git_not_available", "git_precheck")
    if rc != 0:
        return fail("git_not_available", "git_precheck", err)

    # Only tracked-file changes block `git pull --ff-only`; untracked files
    # (data/, tmp/, logs, screenshots) do not. `--untracked-files=no` matches
    # what git pull actually refuses to overwrite.
    rc_dirty, dirty_out, _ = _run_git(
        ["git", "status", "--porcelain", "--untracked-files=no"], repo_path,
    )
    if rc_dirty != 0 or dirty_out:
        return fail("git_working_tree_dirty", "git_precheck", dirty_out[:200])

    # Record pre-update commit
    _, pre_commit, _ = _run_git(["git", "rev-parse", "--short", "HEAD"], repo_path)
    steps.append(_step("git_precheck", UpdateStatus.SUCCESS))

    # Step: git_fetch
    rc, out, err = _run_git(["git", "fetch", remote], repo_path)
    if rc != 0:
        steps.append(_step("git_fetch", UpdateStatus.FAILED, err[:500]))
        return {
            "job_id": job_id, "status": UpdateStatus.FAILED,
            "started_at": started_at,
            "finished_at": datetime.datetime.now().astimezone().isoformat(),
            "steps": steps, "error": "git_fetch_failed",
        }
    steps.append(_step("git_fetch", UpdateStatus.SUCCESS, out[:200]))

    # Step: git_pull_ff_only
    rc, out, err = _run_git(["git", "pull", "--ff-only", remote, branch], repo_path)
    if rc != 0:
        steps.append(_step("git_pull_ff_only", UpdateStatus.FAILED, err[:500]))
        return {
            "job_id": job_id, "status": UpdateStatus.FAILED,
            "started_at": started_at,
            "finished_at": datetime.datetime.now().astimezone().isoformat(),
            "steps": steps, "error": "git_pull_failed",
        }
    _, post_commit, _ = _run_git(["git", "rev-parse", "--short", "HEAD"], repo_path)
    steps.append(_step("git_pull_ff_only", UpdateStatus.SUCCESS, out[:200]))

    # Step: restart_signal
    # Reuse core.platform.exec_restart (the same mechanism /api/server/restart
    # uses). On Unix it closes fd 3..max_fd to release the Hypercorn listen
    # socket, then os.execv replaces the process in-place — same pid, same
    # controlling terminal. On Windows it spawns with CREATE_NEW_PROCESS_GROUP
    # (inherits the parent console stdio) and os._exit(0)s the parent.
    # Either way the user's terminal keeps seeing the server's output rather
    # than being detached into a headless daemon.
    if not skip_restart:
        try:
            import sys as _sys
            import threading as _threading

            from core.platform import exec_restart as _exec_restart

            # Persist the RESTARTING state + post_commit to disk BEFORE
            # scheduling exec_restart, so the polling Chief can still find
            # this job after the peer restarts (load_last_job will auto-heal
            # RESTARTING → SUCCESS once the new process' HEAD matches
            # post_commit).
            if data_dir:
                pre_restart_job = {
                    "job_id": job_id,
                    "status": UpdateStatus.RESTARTING,
                    "started_at": started_at,
                    "finished_at": None,
                    "steps": list(steps) + [_step("restart_signal", UpdateStatus.SUCCESS)],
                    "pre_commit": pre_commit,
                    "post_commit": post_commit,
                    "error": None,
                }
                save_last_job(data_dir, pre_restart_job)

            exec_args = [_sys.executable, *_sys.argv]

            def _delayed_restart():
                import time as _time
                _time.sleep(1.5)  # let the HTTP response flush
                _exec_restart(exec_args)

            _threading.Thread(target=_delayed_restart, daemon=True).start()
        except Exception as exc:
            steps.append(_step("restart_signal", UpdateStatus.FAILED, str(exc)))
            return {
                "job_id": job_id, "status": UpdateStatus.FAILED,
                "started_at": started_at,
                "finished_at": datetime.datetime.now().astimezone().isoformat(),
                "steps": steps, "error": "restart_failed",
            }
    steps.append(_step("restart_signal", UpdateStatus.SUCCESS))

    return {
        "job_id": job_id,
        "status": UpdateStatus.RESTARTING,
        "started_at": started_at,
        "finished_at": None,
        "steps": steps,
        "pre_commit": pre_commit,
        "post_commit": post_commit,
        "error": None,
    }


_MAX_DISPATCH_HISTORY = 10


def _atomic_write(path: Path, data: object) -> None:
    """Write JSON atomically via a .tmp file + os.replace."""
    tmp = path.with_suffix(".json.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


# Process-local cache so concurrent /fleet/update/status queries don't each
# spawn redundant `git rev-parse` + disk re-writes. Keyed by
# (data_dir, job_id, mtime) so file edits invalidate automatically.
_HEAL_CACHE: dict[tuple, dict] = {}


def load_last_job(
    data_dir: str,
    repo_path: str | None = None,
) -> dict | None:
    """Load the last update job from persistent storage.

    If ``repo_path`` is provided and the persisted job is stuck in RESTARTING
    (meaning the peer restart completed successfully but the in-memory state
    was lost across exec), auto-heal by checking whether the current git HEAD
    matches ``post_commit``. If so, upgrade the status to SUCCESS, persist
    once, and cache the healed result so concurrent callers don't re-run
    ``git rev-parse`` for every poll.

    Pass ``repo_path=None`` (the default) to disable heal — callers that
    don't know the repo root get the raw persisted record rather than a
    check against an unrelated ``.`` CWD.
    """
    path = Path(data_dir) / "fleet_update_last.json"
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if repo_path is None or job.get("status") != UpdateStatus.RESTARTING:
        return job

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    cache_key = (data_dir, job.get("job_id"), mtime)
    cached = _HEAL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    post_commit = job.get("post_commit")
    if not post_commit:
        return job

    try:
        rc, head, _ = _run_git(
            ["git", "rev-parse", "--short", "HEAD"], repo_path,
        )
    except Exception as exc:
        logger.warning("load_last_job heal check failed: %s", exc)
        return job

    if rc == 0 and head == post_commit:
        job["status"] = UpdateStatus.SUCCESS
        job["finished_at"] = datetime.datetime.now().astimezone().isoformat()
        save_last_job(data_dir, job)
        try:
            new_mtime = path.stat().st_mtime_ns
        except OSError:
            new_mtime = mtime
        _HEAL_CACHE[(data_dir, job.get("job_id"), new_mtime)] = job
    return job


def save_last_job(data_dir: str, job: dict) -> None:
    """Persist the last update job result (atomic write)."""
    try:
        _atomic_write(Path(data_dir) / "fleet_update_last.json", job)
    except Exception as exc:
        logger.warning("Failed to save fleet_update_last.json: %s", exc)


def load_dispatch_history(data_dir: str) -> list[dict]:
    """Load persisted dispatch history (newest first, max _MAX_DISPATCH_HISTORY entries)."""
    path = Path(data_dir) / "fleet_dispatches.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_dispatch_history(data_dir: str, dispatch_status: dict) -> None:
    """Prepend dispatch_status to history, capping at _MAX_DISPATCH_HISTORY (atomic write)."""
    try:
        history = load_dispatch_history(data_dir)
        dispatch_id = dispatch_status.get("dispatch_id")
        history = [h for h in history if h.get("dispatch_id") != dispatch_id]
        history.insert(0, dispatch_status)
        _atomic_write(Path(data_dir) / "fleet_dispatches.json", history[:_MAX_DISPATCH_HISTORY])
    except Exception as exc:
        logger.warning("Failed to save fleet_dispatches.json: %s", exc)
