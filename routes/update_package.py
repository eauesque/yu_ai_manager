"""Signed update package API routes."""

from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path
from typing import Any

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.repair.update_package import (
    UpdatePackageError,
    apply_update_package,
    rollback_latest_update,
    verify_update_package,
)
from core.system.safe_mode import is_safe_mode
from core.web.auth_helpers import check_mutation_auth

bp = Blueprint("update_package", __name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@bp.route("/api/update/verify", methods=["POST"])
async def api_update_verify():
    err = await check_mutation_auth(request)
    if err:
        return err
    uploaded_tmp: Path | None = None
    try:
        zip_path, uploaded_tmp = await _resolve_zip_from_request()
        result = verify_update_package(zip_path, project_root=PROJECT_ROOT, current_version=_current_version(), current_schema_version=_current_schema_version())
        return api_success({
            "manifest": result.manifest,
            "file_operations": result.file_operations,
            "patch_operations": result.patch_operations,
            "safe_mode": is_safe_mode(),
        })
    except UpdatePackageError as exc:
        return api_error(str(exc), exc.status, code=exc.code)
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 400, code="update_verify_failed")
    finally:
        _cleanup_uploaded_tmp(uploaded_tmp)


@bp.route("/api/update/apply", methods=["POST"])
async def api_update_apply():
    err = await check_mutation_auth(request)
    if err:
        return err
    uploaded_tmp: Path | None = None
    apply_attempted = False
    previous_latest_backup: Path | None = None
    try:
        zip_path, uploaded_tmp = await _resolve_zip_from_request()
        previous_latest_backup = _latest_backup_path()
        apply_attempted = True
        result = apply_update_package(zip_path, project_root=PROJECT_ROOT, current_version=_current_version(), current_schema_version=_current_schema_version())
        return api_success(
            {
                "package_id": result.package_id,
                "applied": result.applied,
                "backup_dir": str(result.backup_dir) if result.backup_dir else None,
                "pending_path": str(result.pending_path) if result.pending_path else None,
            }
        )
    except UpdatePackageError as exc:
        if apply_attempted:
            _rollback_after_apply_error(previous_latest_backup)
        return api_error(str(exc), exc.status, code=exc.code)
    except Exception as exc:  # noqa: BLE001
        if apply_attempted:
            _rollback_after_apply_error(previous_latest_backup)
        return api_error(str(exc), 400, code="update_apply_failed")
    finally:
        _cleanup_uploaded_tmp(uploaded_tmp)


@bp.route("/api/update/rollback", methods=["POST"])
async def api_update_rollback():
    err = await check_mutation_auth(request)
    if err:
        return err
    try:
        result = rollback_latest_update(project_root=PROJECT_ROOT)
        return api_success({"backup_dir": str(result.backup_dir), "restored": result.restored})
    except UpdatePackageError as exc:
        return api_error(str(exc), exc.status, code=exc.code)
    except Exception as exc:  # noqa: BLE001
        return api_error(str(exc), 400, code="update_rollback_failed")


def _rollback_after_apply_error(previous_latest_backup: Path | None) -> None:
    current_latest_backup = _latest_backup_path()
    if current_latest_backup is None or current_latest_backup == previous_latest_backup:
        return
    with contextlib.suppress(Exception):
        rollback_latest_update(project_root=PROJECT_ROOT)


def _latest_backup_path() -> Path | None:
    backup_root = PROJECT_ROOT / "backup"
    try:
        backups = sorted(path for path in backup_root.glob("*") if path.is_dir())
    except OSError:
        return None
    return backups[-1] if backups else None


async def _resolve_zip_from_request() -> tuple[Path, Path | None]:
    form_files = await request.files
    if "file" in form_files:
        upload = form_files["file"]
        with tempfile.NamedTemporaryFile(prefix="update_upload_", suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        await upload.save(tmp_path)
        return tmp_path, tmp_path
    payload: dict[str, Any] = await request.get_json(silent=True) or {}
    raw_path = payload.get("zip_path")
    if not raw_path:
        raise UpdatePackageError("missing_update_zip", "update.zip is required")
    return Path(str(raw_path)).expanduser().resolve(), None


def _cleanup_uploaded_tmp(path: Path | None) -> None:
    if path is not None:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def _current_version() -> str:
    try:
        return str(json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8")).get("version", "0.0.0"))
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


def _current_schema_version() -> int:
    try:
        from core.search_api.server_info import get_meta_int, get_readonly_db

        return int(get_meta_int(get_readonly_db(), "schema_version", 0))
    except Exception:
        return 0
