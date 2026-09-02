"""Self-diagnosis checks for local runtime health."""

from __future__ import annotations

import datetime as dt
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from core.diagnostics.redaction import redact_path
from core.search_api.server_info import get_meta_int, get_readonly_db
from core.services_core.db_cipher import apply_key, sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STALE_UPDATE_PENDING_SECONDS = 7 * 86400

CheckStatus = Literal["OK", "INFO", "WARN", "ERROR"]


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    message: str
    fix_hint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _tool_version(command: str) -> str | None:
    exe = shutil.which(command)
    if not exe:
        return None
    try:
        result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=3, check=False)
    except Exception:
        return None
    lines = (result.stdout or result.stderr).splitlines()
    return lines[0].strip() if lines else None


def _pip_version() -> str | None:
    try:
        return importlib.metadata.version("pip")
    except importlib.metadata.PackageNotFoundError:
        return None


def _project_db_path(project_root: Path) -> Path:
    return Path(os.environ.get("TAGDB_DB", project_root / "data" / "tags.db")).expanduser()


def _check_writable(path: Path) -> CheckResult:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".doctor-", dir=path, delete=True):
            pass
    except Exception as exc:
        return CheckResult("ERROR", f"Writable path failed: {redact_path(path)} ({type(exc).__name__}: {exc})")
    return CheckResult("OK", f"Writable path OK: {redact_path(path)}")


def _dist_status(project_root: Path) -> str:
    candidates = [
        project_root / "ui" / "default" / "static" / "js",
        project_root / "ui" / "default" / "static" / "css",
    ]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return "dist assets missing"
    src_dir = project_root / "src" / "ts"
    try:
        newest_src = max((path.stat().st_mtime for path in src_dir.rglob("*.ts")), default=0.0)
        newest_dist = max(
            (path.stat().st_mtime for root in existing for path in root.rglob("*") if path.is_file()), default=0.0
        )
    except OSError:
        return "dist freshness could not be checked"
    if newest_src and newest_dist and newest_dist < newest_src:
        return "dist assets older than TypeScript sources"
    return "dist assets present"


def _config_status(project_root: Path) -> str:
    from core.configuration.json_rw import candidate_config_paths, load_config_json

    config_path = next(
        (project_root / path for path in candidate_config_paths() if (project_root / path).exists()), None
    )
    if config_path is None:
        return "config missing; defaults or profile config may be used"
    try:
        load_config_json(str(config_path))
    except Exception as exc:
        return f"{config_path.name} parse failed: {type(exc).__name__}"
    return f"{config_path.name} present and parseable"


def _launch_args_status(project_root: Path) -> str:
    path = project_root / "launch-args.txt"
    if not path.exists():
        return "launch-args.txt missing"
    try:
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError as exc:
        return f"launch-args.txt read failed: {type(exc).__name__}"
    return f"launch-args.txt present ({len(lines)} active line(s))"


def _onnxruntime_info() -> str:
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"
    providers = ", ".join(ort.get_available_providers())
    return f"version={getattr(ort, '__version__', 'unknown')}, providers={providers or 'none'}"


def _torch_info() -> str:
    try:
        import torch  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"
    cuda_available = bool(torch.cuda.is_available())
    return f"version={getattr(torch, '__version__', 'unknown')}, cuda_available={cuda_available}"


def _gpu_info() -> str:
    try:
        import torch  # type: ignore[import-not-found]  # noqa: PLC0415
    except Exception as exc:
        return f"GPU name unavailable; VRAM unavailable; capability unavailable ({type(exc).__name__})"
    if not torch.cuda.is_available():
        return "GPU name unavailable; VRAM unavailable; capability unavailable (CUDA unavailable)"
    try:
        device = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(device)
        vram_gb = round(props.total_memory / (1024**3), 2)
        capability = ".".join(str(part) for part in torch.cuda.get_device_capability(device))
        return f"GPU name={props.name}; VRAM={vram_gb} GiB; capability={capability}"
    except Exception as exc:
        return f"GPU name unavailable; VRAM unavailable; capability unavailable ({type(exc).__name__})"


def _known_incompatibilities() -> list[str]:
    issues: list[str] = []
    onnx = _onnxruntime_info()
    torch_info = _torch_info()
    if "CUDAExecutionProvider" in onnx and "cuda_available=False" in torch_info:
        issues.append("ONNX Runtime has CUDAExecutionProvider but torch reports CUDA unavailable")
    if sys.version_info >= (3, 13) and "torch unavailable" in torch_info:
        issues.append("Python 3.13 with missing torch may require a compatible wheel before GPU features work")
    return issues


def _check_python() -> CheckResult:
    return CheckResult(
        "OK",
        f"Python version={platform.python_version()}, executable={redact_path(sys.executable)}, venv={redact_path(sys.prefix)}",
    )


def _check_tooling() -> list[CheckResult]:
    uv = _tool_version("uv")
    pip = _pip_version()
    node = _tool_version("node")
    pnpm = _tool_version("pnpm")
    return [
        CheckResult("OK" if uv else "WARN", f"uv={uv or 'not found'}"),
        CheckResult("OK" if pip else "WARN", f"pip={pip or 'not installed'}"),
        CheckResult("OK" if node else "WARN", f"Node.js={node or 'not found'}"),
        CheckResult("OK" if pnpm else "WARN", f"pnpm={pnpm or 'not found'}"),
    ]


def _check_db_schema(db_path: Path) -> CheckResult:
    try:
        con = get_readonly_db()
        schema_version = get_meta_int(con, "schema_version", -1)
    except Exception as exc:
        return CheckResult(
            "ERROR",
            f"DB path={redact_path(db_path)}, schema_version unavailable ({type(exc).__name__}: {exc})",
            "Check that tags.db exists and can be opened read-only.",
        )
    return CheckResult("OK", f"DB path={redact_path(db_path)}, schema_version={schema_version}")


def _check_db_integrity(db_path: Path) -> CheckResult:
    """Quick integrity check using PRAGMA quick_check only (avoids full table scan)."""
    if not db_path.exists():
        return CheckResult("ERROR", f"DB file not found: {redact_path(db_path)}", "Check that tags.db exists.")
    try:
        con = sqlite3.connect(str(db_path))
        apply_key(con)
        result = con.execute("PRAGMA quick_check").fetchone()
        con.close()
    except Exception as exc:
        return CheckResult(
            "ERROR",
            f"DB quick_check failed: {type(exc).__name__}: {exc}",
            "Run the dedicated DB health repair flow only after backing up user data.",
        )
    if not result or result[0] != "ok":
        return CheckResult(
            "ERROR",
            f"DB quick_check reported issues: {redact_path(db_path)} ({result})",
            "Run the dedicated DB health repair flow only after backing up user data.",
        )
    return CheckResult("OK", f"DB quick_check OK: {redact_path(db_path)}")


def _check_update_pending(project_root: Path, now: dt.datetime | None = None) -> list[CheckResult]:
    pending_dir = project_root / "data" / "update_pending"
    if not pending_dir.exists():
        return [CheckResult("INFO", f"data/update_pending residuals: none ({redact_path(pending_dir)})")]
    current = now or dt.datetime.now(dt.UTC)
    results: list[CheckResult] = []
    for path in sorted(pending_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created_at_raw = str(data["created_at"])
            created_at = dt.datetime.fromisoformat(created_at_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=dt.UTC)
            age_seconds = (current - created_at.astimezone(dt.UTC)).total_seconds()
        except Exception as exc:
            results.append(
                CheckResult("WARN", f"data/update_pending residual unreadable: {path.name} ({type(exc).__name__})")
            )
            continue
        status: CheckStatus = "WARN" if age_seconds > STALE_UPDATE_PENDING_SECONDS else "INFO"
        age_days = round(age_seconds / 86400, 1)
        results.append(
            CheckResult(
                status, f"data/update_pending residual: {path.name}, created_at={created_at_raw}, age_days={age_days}"
            )
        )
    if not results:
        results.append(CheckResult("INFO", f"data/update_pending residuals: none ({redact_path(pending_dir)})"))
    return results


def cleanup_stale_update_pending(
    project_root: Path,
    max_age_days: int = 7,
    now: dt.datetime | None = None,
) -> tuple[int, list[str]]:
    """Delete update_pending JSON entries older than *max_age_days*.

    Returns (deleted_count, list_of_deleted_filenames).
    Unreadable files are also removed (they can never be applied).
    """
    pending_dir = project_root / "data" / "update_pending"
    if not pending_dir.exists():
        return 0, []
    current = now or dt.datetime.now(dt.UTC)
    cutoff = max_age_days * 86400
    deleted: list[str] = []
    for path in sorted(pending_dir.glob("*.json")):
        remove = False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created_at_raw = str(data["created_at"])
            created_at = dt.datetime.fromisoformat(created_at_raw)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=dt.UTC)
            age_seconds = (current - created_at.astimezone(dt.UTC)).total_seconds()
            if age_seconds > cutoff:
                remove = True
        except Exception:
            remove = True
        if remove:
            try:
                path.unlink(missing_ok=True)
                deleted.append(path.name)
            except OSError:
                pass
    return len(deleted), deleted


def run_all_checks(
    *,
    project_root: Path | None = None,
    db_path: Path | None = None,
    now: dt.datetime | None = None,
) -> list[CheckResult]:
    root = (project_root or PROJECT_ROOT).resolve()
    resolved_db_path = (db_path or _project_db_path(root)).resolve()
    results: list[CheckResult] = []
    results.append(_check_python())
    results.extend(_check_tooling())
    dist_status = _dist_status(root)
    results.append(
        CheckResult(
            "WARN" if "older" in dist_status or "missing" in dist_status else "OK", f"dist freshness: {dist_status}"
        )
    )
    results.append(_check_db_schema(resolved_db_path))
    results.append(_check_db_integrity(resolved_db_path))
    for path in [root / "reports", root / "repair", root / "logs", root / "data"]:
        results.append(_check_writable(path))
    results.append(CheckResult("INFO", f"config: {_config_status(root)}"))
    results.append(CheckResult("INFO", f"launch-args: {_launch_args_status(root)}"))
    results.append(CheckResult("INFO", f"log dir: {redact_path(root / 'logs')}"))
    results.append(CheckResult("INFO", f"ONNX Runtime providers: {_onnxruntime_info()}"))
    results.append(CheckResult("INFO", f"torch / CUDA: {_torch_info()}"))
    results.append(CheckResult("INFO", _gpu_info()))
    incompatibilities = _known_incompatibilities()
    if incompatibilities:
        results.extend(CheckResult("WARN", f"Known incompatible combination: {issue}") for issue in incompatibilities)
    else:
        results.append(CheckResult("OK", "Known incompatible combinations: none detected"))
    results.extend(_check_update_pending(root, now=now))
    return results
