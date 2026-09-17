"""Training command generation and execution API handlers."""

from __future__ import annotations

import os
import threading

from quart import Blueprint, request

from core.event_bus import emit
from core.infra_core.api_errors import api_error, api_result

from . import store
from .kohya_runner import build_train_args, build_train_command, run_train


def _find_latest_state(output_dir: str) -> str | None:
    """Find the latest saved training state directory.

    kohya_ss saves states as {output_dir}/{output_name}-state/ or
    {output_dir}/{output_name}_e{epoch}-state/ directories.
    """
    if not output_dir or not os.path.isdir(output_dir):
        return None
    candidates = []
    try:
        for entry in os.scandir(output_dir):
            if entry.is_dir() and entry.name.endswith("-state"):
                candidates.append(entry)
    except OSError:
        return None
    if not candidates:
        return None
    # Sort by modification time descending, return the newest
    candidates.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    return candidates[0].path

# Simple state tracker for training jobs
_train_state: dict = {"running": False, "pid": None, "log": []}


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register(bp: Blueprint) -> None:
    """Register training routes on the blueprint."""

    @bp.route("/projects/<int:pid>/train", methods=["POST"])
    async def start_train(pid: int):
        proj = store.get_project(pid)
        if not proj:
            return api_error("Project not found", 404)

        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
        )
        kohya_path = get_extension_config_value(
            "builtin-lora-dataset-manager", "kohya_path", ""
        )
        if not kohya_path:
            return api_error("kohya_path not configured", 400)

        data = await request.get_json(silent=True) or {}
        checkpoint_path = (data.get("checkpoint") or "").strip()
        if not checkpoint_path:
            return api_error("checkpoint path is required", 400)

        # Validate checkpoint is a real file inside checkpoint_dir
        checkpoint_dir = get_extension_config_value(
            "builtin-lora-dataset-manager", "checkpoint_dir", ""
        )
        if not checkpoint_dir:
            return api_error("checkpoint_dir not configured", 400)
        try:
            real_ckpt = os.path.realpath(checkpoint_path)
            real_dir = os.path.realpath(checkpoint_dir)
            if not real_ckpt.startswith(real_dir + os.sep):
                return api_error(
                    "checkpoint must be inside checkpoint_dir", 403,
                )
        except (OSError, ValueError):
            return api_error("invalid checkpoint path", 400)
        if not os.path.isfile(real_ckpt):
            return api_error("checkpoint file not found", 404)

        output_base = get_extension_config_value(
            "builtin-lora-dataset-manager", "output_base_dir", ""
        )
        if not output_base:
            return api_error("output_base_dir not configured", 400)

        safe_name = "".join(
            c if c.isalnum() or c in "-_ " else "_" for c in proj.name
        )
        dataset_dir = os.path.join(output_base, safe_name)
        output_dir = os.path.join(output_base, safe_name, "output")
        os.makedirs(output_dir, exist_ok=True)

        # Merge per-request extra_args with config
        req_extra = data.get("extra_args")
        extra_override = None
        if isinstance(req_extra, list) and req_extra:
            extra_override = " ".join(str(a) for a in req_extra)

        # Resume: auto-detect latest state or use explicit path
        resume_from = None
        if data.get("resume"):
            resume_path = data.get("resume_from", "")
            if resume_path and isinstance(resume_path, str):
                resume_from = resume_path.strip()
            else:
                resume_from = _find_latest_state(output_dir)

        train_args = build_train_args(
            kohya_path=kohya_path,
            checkpoint_path=real_ckpt,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            base_model=proj.base_model,
            project_name=proj.name,
            extra_args_override=extra_override,
            resume_from=resume_from,
        )
        command_display = build_train_command(
            kohya_path=kohya_path,
            checkpoint_path=real_ckpt,
            dataset_dir=dataset_dir,
            output_dir=output_dir,
            base_model=proj.base_model,
            project_name=proj.name,
            extra_args_override=extra_override,
            resume_from=resume_from,
        )

        if _train_state["running"]:
            return api_error("Training already in progress", 429)

        if data.get("dry_run"):
            result = {"command": command_display, "dry_run": True}
            if resume_from:
                result["resume_from"] = resume_from
            return api_result(result, 200)

        _train_state["running"] = True
        _train_state["log"] = []
        _train_state["pid"] = None

        # Log file for detached process output
        log_file = os.path.join(output_dir, "train.log")
        _train_state["log_file"] = log_file

        def _emit_line(line: str):
            _train_state["log"].append(line)
            if len(_train_state["log"]) > 5000:
                _train_state["log"] = _train_state["log"][-2500:]
            emit("lora_train.output", {"line": line})

        def _worker():
            try:
                emit("lora_train.start", {"project_id": pid, "command": command_display})
                proc = run_train(
                    train_args, cwd=kohya_path,
                    log_file=log_file, emit_progress=_emit_line,
                )
                if proc is None:
                    _train_state["running"] = False
                    emit("lora_train.complete", {"error": "Failed to start process"})
                    return
                _train_state["pid"] = proc.pid
                proc.wait()
                code = proc.returncode
                emit("lora_train.complete", {
                    "project_id": pid, "returncode": code,
                    "success": code == 0,
                })
            except Exception as exc:
                emit("lora_train.complete", {"error": str(exc)})
            finally:
                _train_state["running"] = False
                _train_state["pid"] = None

        threading.Thread(target=_worker, daemon=True).start()

        return api_result({
            "accepted": True,
            "command": command_display,
            "message": "Training started",
        }, 202)

    @bp.route("/projects/<int:pid>/train/status", methods=["GET"])
    async def train_status(pid: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        tail = request.args.get("tail", 50, type=int)
        result = {
            "running": _train_state["running"],
            "pid": _train_state["pid"],
            "log_tail": _train_state["log"][-tail:],
            "log_total": len(_train_state["log"]),
        }
        log_file = _train_state.get("log_file", "")
        if log_file:
            result["log_file"] = log_file
        return api_result(result, 200)

    @bp.route("/checkpoints", methods=["GET"])
    async def list_checkpoints():
        """Scan checkpoint directory for model files."""
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
        )
        ckpt_dir = get_extension_config_value(
            "builtin-lora-dataset-manager", "checkpoint_dir", ""
        )
        if not ckpt_dir or not os.path.isdir(ckpt_dir):
            return api_result({"checkpoints": [], "error": "checkpoint_dir not set or not found"}, 200)

        exts = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}
        files = []
        try:
            for entry in os.scandir(ckpt_dir):
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in exts:
                    files.append({
                        "name": entry.name,
                        "path": entry.path,
                        "size": entry.stat().st_size,
                    })
        except OSError:
            pass
        files.sort(key=lambda f: f["name"].lower())
        return api_result({"checkpoints": files}, 200)
