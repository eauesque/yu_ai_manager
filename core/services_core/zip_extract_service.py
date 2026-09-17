"""Synchronous helpers for archive member extraction and DB registration."""

from __future__ import annotations

import datetime as _dt
import os
import zipfile
from pathlib import Path
from typing import Any

from core.configuration.api import load_config
from core.infra_core.debug_log import dlog
from core.scan_core.scanner import scan_one


def _validate_internal_path(internal_path: str) -> bool:
    if "\x00" in internal_path:
        return False
    normalized = internal_path.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    return ".." not in normalized.split("/")


def _verify_extracted_path(extracted_path: str, extract_dir: str) -> bool:
    real_extracted = Path(extracted_path).resolve()
    real_extract_dir = Path(extract_dir).resolve()
    try:
        real_extracted.relative_to(real_extract_dir)
        return True
    except ValueError:
        return False


def _is_7z_archive(archive_path: str) -> bool:
    return archive_path.lower().endswith(".7z")


def _is_rar_archive(archive_path: str) -> bool:
    return archive_path.lower().endswith(".rar")


def validate_extract_target(con, file_id: Any):
    if not file_id:
        return None, ({"error": "file_id is required", "code": "missing_file_id"}, 400)
    row = con.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
    if not row or "!" not in row["path"]:
        return None, ({"error": "アーカイブ内ファイルではありません", "code": "not_zip_member"}, 400)
    return row["path"].split("!", 1), None


def extract_zip_member(zip_path: str, internal_path: str) -> tuple[str, Any]:
    if _is_7z_archive(zip_path):
        return _extract_7z_member(zip_path, internal_path)
    if _is_rar_archive(zip_path):
        return _extract_rar_member(zip_path, internal_path)
    return _extract_zip_member(zip_path, internal_path)


def _extract_zip_member(zip_path: str, internal_path: str) -> tuple[str, Any]:
    if not os.path.exists(zip_path):
        return "", (
            {
                "error": "ZIPファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元ZIPが移動/削除されていないか確認してください",
            },
            404,
        )
    if not _validate_internal_path(internal_path):
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)

    extract_dir = os.path.join(os.path.dirname(zip_path), "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            extracted_path = zf.extract(internal_path, extract_dir)
    except zipfile.BadZipFile:
        return "", ({"error": "ZIPファイルが破損しているため解凍できません", "code": "bad_zip_file"}, 422)
    except KeyError:
        return "", (
            {
                "error": "ZIP内に対象ファイルが見つかりません",
                "code": "zip_entry_not_found",
                "hint": "再スキャンでZIP内エントリを更新してください",
            },
            404,
        )

    if not _verify_extracted_path(extracted_path, extract_dir):
        if os.path.exists(extracted_path):
            os.unlink(extracted_path)
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)
    return extracted_path, None


def _extract_7z_member(archive_path: str, internal_path: str) -> tuple[str, Any]:
    if not os.path.exists(archive_path):
        return "", (
            {
                "error": "7zファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元7zが移動/削除されていないか確認してください",
            },
            404,
        )
    if not _validate_internal_path(internal_path):
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)

    from core.sevenz_core.sevenz_cli import extract_to_dir, sevenz_available

    if not sevenz_available():
        return "", ({"error": "7z CLI が必要です (7-Zip をインストールしてください)", "code": "missing_dependency"}, 500)

    extract_dir = os.path.join(os.path.dirname(archive_path), "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        extract_to_dir(archive_path, extract_dir, targets=[internal_path])
    except Exception as exc:
        err_str = str(exc).lower()
        if "corrupt" in err_str or "bad" in err_str or "cannot open" in err_str:
            return "", (
                {
                    "error": "7z file is corrupted",
                    "code": "bad_zip_file",
                    "zip_path": archive_path,
                    "entry": internal_path,
                },
                422,
            )
        return "", (
            {
                "error": "7z extraction failed",
                "code": "zip_entry_not_found",
                "hint": "Rescan to update 7z entries",
            },
            404,
        )

    extracted_path = os.path.join(extract_dir, internal_path.replace("/", os.sep))
    if not _verify_extracted_path(extracted_path, extract_dir):
        if os.path.exists(extracted_path):
            os.unlink(extracted_path)
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)
    if not os.path.exists(extracted_path):
        return "", (
            {
                "error": "7z内に対象ファイルが見つかりません",
                "code": "zip_entry_not_found",
                "hint": "再スキャンで7z内エントリを更新してください",
            },
            404,
        )
    return extracted_path, None


def _extract_rar_member(archive_path: str, internal_path: str) -> tuple[str, Any]:
    if not os.path.exists(archive_path):
        return "", (
            {
                "error": "RARファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元RARが移動/削除されていないか確認してください",
            },
            404,
        )
    if not _validate_internal_path(internal_path):
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)

    try:
        import rarfile
    except ImportError:
        return "", ({"error": "rarfile が必要です (pip install rarfile)", "code": "missing_dependency"}, 500)

    extract_dir = os.path.join(os.path.dirname(archive_path), "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with rarfile.RarFile(archive_path, "r") as rf:
            rf.extract(internal_path, extract_dir)
    except Exception as exc:
        if "Bad" in type(exc).__name__:
            return "", (
                {
                    "error": "RARファイルが破損しているため解凍できません",
                    "code": "bad_zip_file",
                    "zip_path": archive_path,
                    "entry": internal_path,
                },
                422,
            )
        return "", (
            {
                "error": "RAR解凍に失敗しました",
                "code": "zip_entry_not_found",
                "hint": "再スキャンでRAR内エントリを更新してください",
            },
            404,
        )

    extracted_path = os.path.join(extract_dir, internal_path.replace("/", os.sep))
    if not _verify_extracted_path(extracted_path, extract_dir):
        if os.path.exists(extracted_path):
            os.unlink(extracted_path)
        return "", ({"error": "Path traversal blocked", "code": "zip_path_traversal"}, 400)
    if not os.path.exists(extracted_path):
        return "", (
            {
                "error": "RAR内に対象ファイルが見つかりません",
                "code": "zip_entry_not_found",
                "hint": "再スキャンでRAR内エントリを更新してください",
            },
            404,
        )
    return extracted_path, None


def register_extracted_file(con, file_id: Any, new_path: str, zip_path: str, internal_path: str):
    config = load_config(None)
    scan_one(con, Path(new_path), config, force=True, compute_hash=False)
    new_row = con.execute("SELECT id FROM files WHERE path=?", (new_path,)).fetchone()
    if not new_row:
        return None
    new_id = new_row["id"]
    con.execute(
        """
        UPDATE files
        SET extracted_from_zip=?,
            extracted_from_internal=?,
            extraction_date=?
        WHERE id=?
        """,
        (zip_path, internal_path, int(_dt.datetime.now(tz=_dt.UTC).timestamp()), new_id),
    )
    con.execute(
        """
        UPDATE files
        SET extracted_to_file_id=?
        WHERE id=?
        """,
        (new_id, file_id),
    )
    con.commit()
    return new_id


def extract_from_archive(file_id: Any, remote_addr: str):
    """Extract one archive member and register the extracted file in DB."""
    from core.services_core.db_api import get_db

    dlog("zip", "extract.request", file_id=file_id, remote_addr=remote_addr)

    con = get_db()
    target, err = validate_extract_target(con, file_id)
    if err:
        reason = "missing_file_id" if not file_id else "not_zip_member"
        dlog("zip", "extract.bad_request", reason=reason, file_id=file_id)
        return err
    zip_path, internal_path = target
    dlog("zip", "extract.target", zip_path=zip_path, internal_path=internal_path)

    new_path, extract_err = extract_zip_member(zip_path, internal_path)
    if extract_err:
        dlog("zip", "extract.failed", zip_path=zip_path, internal_path=internal_path)
        return extract_err

    new_id = register_extracted_file(con, file_id, new_path, zip_path, internal_path)
    if new_id is None:
        dlog("zip", "extract.register_failed", new_path=new_path)
        return {"error": "Failed to register extracted file", "code": "extract_register_failed"}, 500

    dlog("zip", "extract.success", new_file_id=new_id, new_path=new_path)
    return {"success": True, "new_path": new_path, "new_file_id": new_id}, 200
