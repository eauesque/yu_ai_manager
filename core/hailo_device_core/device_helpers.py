"""Pure helper functions for Hailo device management (no module state)."""

import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CMA event logging
# ---------------------------------------------------------------------------
#
# Append one line per VDevice / model acquire / release event to a dedicated
# log so CmaFree transitions around model operations and our VDevice-retention
# strategy can be measured separately over hours-to-days of runtime. CmaFree is
# telemetry; its absolute value is not an allocation-capacity verdict.
#
# Format (key=value, space-delimited, fields-after-event are optional):
#   <iso-ts> event=<name> cma_free_mb=<int|none> [owner=<str>] [hef=<basename>] [note=<...>]
#
# Compute deltas with awk:
#   awk -F 'cma_free_mb=' '{print $2}' logs/hailo_cma.log \
#     | awk '{prev=cur; cur=$1; if (NR>1) print NR, cur-prev}'
#
# Or filter by event:
#   grep 'event=release_post' logs/hailo_cma.log | tail -50
#
# The file lives next to logs/error.log and is created on demand. Failures to
# log are swallowed silently so instrumentation never breaks the Hailo path.

_HAILO_CMA_LOG_LOCK = threading.Lock()
_HAILO_CMA_LOG_PATH: Path | None = None
_HAILO_CMA_LOG_PATH_RESOLVED = False


def _resolve_hailo_cma_log_path() -> Path | None:
    """Cache and return the absolute path of logs/hailo_cma.log."""
    global _HAILO_CMA_LOG_PATH, _HAILO_CMA_LOG_PATH_RESOLVED
    if _HAILO_CMA_LOG_PATH_RESOLVED:
        return _HAILO_CMA_LOG_PATH
    with _HAILO_CMA_LOG_LOCK:
        if _HAILO_CMA_LOG_PATH_RESOLVED:
            return _HAILO_CMA_LOG_PATH
        try:
            from core.services_core.app_runtime_state import get_db_path
            # logs/ is a sibling of data/ (where tags.db lives).
            base = get_db_path().resolve().parent.parent / "logs"
        except Exception:
            base = Path("logs")
        try:
            base.mkdir(parents=True, exist_ok=True)
            _HAILO_CMA_LOG_PATH = base / "hailo_cma.log"
        except Exception:
            _HAILO_CMA_LOG_PATH = None
        _HAILO_CMA_LOG_PATH_RESOLVED = True
        return _HAILO_CMA_LOG_PATH


def _format_cma_event(
    event: str,
    cma_free_mb: int | None,
    *,
    owner: str | None = None,
    hef: str | None = None,
    note: str | None = None,
) -> str:
    parts = [
        time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        f"event={event}",
        f"cma_free_mb={'none' if cma_free_mb is None else cma_free_mb}",
        f"pid={os.getpid()}",
    ]
    if owner is not None:
        parts.append(f"owner={owner}")
    if hef is not None:
        parts.append(f"hef={os.path.basename(hef)}")
    if note is not None:
        # Strip newlines so each log line stays one record for grep/awk.
        parts.append("note=" + note.replace("\n", " ").replace("\r", " "))
    return " ".join(parts) + "\n"


def log_hailo_cma_event(
    event: str,
    *,
    owner: str | None = None,
    hef: str | None = None,
    note: str | None = None,
) -> None:
    """Append one CMA event line to ``logs/hailo_cma.log``.

    Reads ``CmaFree`` from ``/proc/meminfo`` at call time so each event line
    captures the kernel-visible CMA state *as the Hailo path observes it*.
    Never raises — instrumentation must not break the production Hailo
    acquire / release paths.

    Common events: ``vdevice_create_pre`` / ``vdevice_create_post`` /
    ``vdevice_reuse`` / ``acquire_pre`` / ``acquire_post`` /
    ``acquire_failed`` / ``release_pre`` / ``release_post`` /
    ``shutdown_pre`` / ``shutdown_post``.
    """
    path = _resolve_hailo_cma_log_path()
    if path is None:
        return
    free_mb = _read_cma_free_mb()
    line = _format_cma_event(
        event, free_mb, owner=owner, hef=hef, note=note,
    )
    try:
        with _HAILO_CMA_LOG_LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        # Disk full, perm error, etc. — never let instrumentation fail Hailo ops.
        return


# ---------------------------------------------------------------------------
# CMA pre-flight check helpers
# ---------------------------------------------------------------------------

# Conservative CMA estimates (MB) per model HEF path substring.
# Slightly over-estimated on purpose — a false warning is better than a hang.
_CMA_ESTIMATES_MB: list = [
    ("whisper-small",  175),
    ("whisper_small",  175),
    ("whisper-base",   115),
    ("whisper_base",   115),
    ("whisper-tiny",    85),
    ("whisper_tiny",    85),
    ("whisper",        180),   # unknown whisper size → conservative
    ("qwen",           300),   # LLM family. qwen2.5-1.5b ~234 MB (2026-04-15),
                               # qwen3-1.7b-instruct 285 MB measured 2026-05-17
                               # from logs/hailo_cma.log (acquire_pre 393 →
                               # acquire_post 108). +15 MB margin over 285.
    ("llava",          300),   # VLM family — conservative
]

_CMA_DEFAULT_MB = 260  # fallback for unrecognised paths


def _read_cma_free_mb() -> int | None:
    """Return CmaFree in MB from /proc/meminfo, or None if unavailable."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                m = re.match(r"CmaFree:\s+(\d+)", line)
                if m:
                    return int(m.group(1)) // 1024
    except (OSError, ValueError):
        pass
    return None


def _read_cma_total_mb() -> int | None:
    """Return CmaTotal in MB from /proc/meminfo, or None if unavailable."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                m = re.match(r"CmaTotal:\s+(\d+)", line)
                if m:
                    return int(m.group(1)) // 1024
    except (OSError, ValueError):
        pass
    return None


def _estimate_cma_mb(model_path: str) -> int:
    """Return estimated CMA usage in MB for a GenAI HEF path."""
    p = model_path.lower()
    for substr, mb in _CMA_ESTIMATES_MB:
        if substr in p:
            return mb
    return _CMA_DEFAULT_MB


def _extract_all_quant_params(infer_model) -> list[dict]:
    """Extract quantization parameters for every output tensor."""
    params: list[dict] = []
    for out in infer_model.outputs:
        try:
            qp = out.quant_infos[0]
            scale = float(qp.qp_scale)
            zp = float(qp.qp_zp)
        except (AttributeError, IndexError, TypeError) as exc:
            logger.warning(
                "Could not extract quant params for %s: %s. Defaults.",
                getattr(out, "name", "?"), exc,
            )
            scale, zp = 1.0, 0.0

        # Detect output dtype: NMS-postprocess outputs are float32
        dtype = "uint8"
        try:
            fmt = out.format.type
            fmt_name = str(fmt).lower()
            if "float32" in fmt_name or "float" in fmt_name:
                dtype = "float32"
        except (AttributeError, Exception):
            # Heuristic: scale=1.0 + zp=0.0 + "nms" in name => float32
            name = getattr(out, "name", "")
            if scale == 1.0 and zp == 0.0 and "nms" in name.lower():
                dtype = "float32"

        params.append({
            "name": getattr(out, "name", "unknown"),
            "shape": tuple(out.shape),
            "scale": scale,
            "zero_point": zp,
            "dtype": dtype,
        })
    return params
