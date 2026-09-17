"""kohya_ss train command builder and runner.

Generates training command strings for kohya_ss / sd-scripts.
Optionally executes them as a subprocess with SSE progress streaming.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)


def _resolve_kohya_python(kohya_path: str) -> str:
    """Resolve the Python interpreter for kohya_ss.

    Priority: config override > kohya_ss venv > current interpreter.
    """
    # 1. Config override
    try:
        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
        )
        custom = get_extension_config_value(
            "builtin-lora-dataset-manager", "kohya_python_path", ""
        )
        if custom and os.path.isfile(custom):
            return custom
    except Exception:
        logger.warning("custom kohya python path could not be read", exc_info=True)

    # 2. kohya_ss own venv -- check kohya_path and its parent
    #    (sd-scripts may be nested inside a kohya_ss wrapper dir)
    candidates = [kohya_path, os.path.dirname(kohya_path)]
    for base in candidates:
        venv_win = os.path.join(base, "venv", "Scripts", "python.exe")
        venv_unix = os.path.join(base, "venv", "bin", "python")
        if os.path.isfile(venv_win):
            return venv_win
        if os.path.isfile(venv_unix):
            return venv_unix

    # 3. Fallback to current interpreter
    return sys.executable


def _get_train_config() -> dict:
    """Load training parameters from extension config with defaults."""
    defaults = {
        "train_network_dim": 32,
        "train_network_alpha": 16,
        "train_learning_rate": "1e-4",
        "train_max_epochs": 10,
        "train_save_every_n_epochs": 2,
        "train_extra_args": "",
    }
    try:
        from core.extensions_core.lifecycle.extensions_admin import (
            get_extension_config_value,
        )
        return {
            k: get_extension_config_value(
                "builtin-lora-dataset-manager", k, v,
            )
            for k, v in defaults.items()
        }
    except Exception:
        return defaults


def build_train_args(
    kohya_path: str,
    checkpoint_path: str,
    dataset_dir: str,
    output_dir: str,
    base_model: str,
    project_name: str,
    extra_args_override: str | None = None,
    resume_from: str | None = None,
) -> list[str]:
    """Build the kohya_ss training command as an argument list.

    Returns a list of arguments safe for subprocess (no shell interpretation).
    Training parameters are read from extension config.
    extra_args_override: if provided, appended AFTER config extra_args.
    resume_from: path to a saved training state dir for --resume.
    """
    # Prefer sd-scripts subfolder, fall back to top-level
    script = "sdxl_train_network.py" if base_model == "sdxl" else "train_network.py"
    sd_scripts_path = os.path.join(kohya_path, "sd-scripts", script)
    top_path = os.path.join(kohya_path, script)
    script_path = sd_scripts_path if os.path.isfile(sd_scripts_path) else top_path

    python = _resolve_kohya_python(kohya_path)
    cfg = _get_train_config()

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
    resolution = "1024,1024" if base_model == "sdxl" else "512,512"

    args = [
        python,
        script_path,
        f"--pretrained_model_name_or_path={checkpoint_path}",
        f"--train_data_dir={dataset_dir}",
        f"--output_dir={output_dir}",
        f"--output_name={safe_name}",
        "--network_module=networks.lora",
        f"--network_dim={cfg['train_network_dim']}",
        f"--network_alpha={cfg['train_network_alpha']}",
        f"--learning_rate={cfg['train_learning_rate']}",
        f"--max_train_epochs={cfg['train_max_epochs']}",
        f"--save_every_n_epochs={cfg['train_save_every_n_epochs']}",
        "--mixed_precision=fp16",
        f"--resolution={resolution}",
        "--cache_latents_to_disk",
        "--gradient_checkpointing",
        "--xformers",
        "--save_state",
    ]

    if base_model == "sdxl":
        args.append("--cache_text_encoder_outputs")
        args.append("--network_train_unet_only")

    # Resume from saved training state
    if resume_from and os.path.isdir(resume_from):
        args.append(f"--resume={resume_from}")

    # Append user-defined extra arguments (config + per-request override)
    # Deny flags that would override security-validated parameters
    import shlex
    for extra in [
        str(cfg.get("train_extra_args", "")).strip(),
        (extra_args_override or "").strip(),
    ]:
        if extra:
            try:
                parts = shlex.split(extra)
            except ValueError:
                parts = extra.split()
            for part in parts:
                key = part.split("=", 1)[0].lstrip("-")
                if key in _DENIED_EXTRA_FLAGS:
                    logger.warning("Blocked denied flag in extra_args: %s", part)
                    continue
                args.append(part)

    return args


# Flags that must not be overridden via extra_args
_DENIED_EXTRA_FLAGS = frozenset({
    "output_dir", "output_name",
    "pretrained_model_name_or_path",
    "train_data_dir",
    "resume",
    "network_module",
})


def build_train_command(
    kohya_path: str,
    checkpoint_path: str,
    dataset_dir: str,
    output_dir: str,
    base_model: str,
    project_name: str,
    extra_args_override: str | None = None,
    resume_from: str | None = None,
) -> str:
    """Build a display-friendly command string (for dry_run preview only)."""
    import shlex
    args = build_train_args(
        kohya_path, checkpoint_path, dataset_dir, output_dir,
        base_model, project_name, extra_args_override, resume_from,
    )
    return " ".join(shlex.quote(a) for a in args)


def run_train(
    args: list[str],
    cwd: str,
    log_file: str = "",
    emit_progress=None,
) -> subprocess.Popen | None:
    """Execute training command as a detached subprocess.

    The process is detached from the parent so it survives server restarts.
    Output is written to log_file and tailed for SSE streaming.

    Args:
        args: Argument list from build_train_args().
        cwd: Working directory (kohya_path).
        log_file: Path to write stdout/stderr. If empty, uses pipe (legacy).
        emit_progress: Optional callback(line: str) for SSE streaming.

    Returns:
        Popen object for the running process, or None on failure.
    """
    # Platform-specific flags to detach the child process
    kwargs: dict = {}
    if sys.platform == "win32":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    log_fh = None
    try:
        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            log_fh = open(log_file, "w", encoding="utf-8", errors="replace")  # noqa: SIM115
            stdout_target = log_fh
        else:
            stdout_target = subprocess.PIPE

        proc = subprocess.Popen(
            args,
            shell=False,
            cwd=cwd,
            stdout=stdout_target,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
    except OSError as exc:
        logger.error("Failed to start training: %s", exc)
        if log_fh:
            log_fh.close()
        return None

    if emit_progress:
        def _stream():
            try:
                if log_file:
                    # Tail the log file for SSE streaming
                    _tail_log(log_file, proc, emit_progress)
                elif proc.stdout:
                    for line in proc.stdout:
                        emit_progress(line.rstrip("\n"))
            except Exception:
                logger.warning("training progress stream stopped early", exc_info=True)
            finally:
                if log_fh:
                    log_fh.close()
        threading.Thread(target=_stream, daemon=True).start()

    return proc


def _tail_log(log_path: str, proc: subprocess.Popen, emit, poll_interval: float = 0.5):
    """Tail a log file while the process is running."""
    import time
    with open(log_path, encoding="utf-8", errors="replace") as f:
        while proc.poll() is None:
            line = f.readline()
            if line:
                emit(line.rstrip("\n"))
            else:
                time.sleep(poll_interval)
        # Read remaining lines after process exits
        for line in f:
            emit(line.rstrip("\n"))
