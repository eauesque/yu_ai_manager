"""Chatlog API: import routes and helper functions.

Split from api.py to keep each module under 300 lines.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
import threading
import zipfile
from typing import Any

from quart import Blueprint, jsonify, request

from core.services_core.db_write import submit_db_write

from .importer import VALID_SOURCES, ImportJob

logger = logging.getLogger(__name__)

# Import job (only one globally)
_import_job: ImportJob | None = None
_import_lock = threading.Lock()

# ZIP extraction size limit (200 MB)
_ZIP_MAX_SIZE = 200 * 1024 * 1024
_IMPORT_MAX_SIZE = 50 * 1024 * 1024
_READ_CHUNK_SIZE = 1024 * 1024


def register_import_routes(bp: Blueprint) -> None:
    """Register import-related routes on the chatlog blueprint."""

    # -- API: import (multipart, for browser) --

    @bp.route("/api/import", methods=["POST"])
    async def api_import():
        global _import_job

        source = (await request.form).get("source", "").strip()
        if source not in VALID_SOURCES:
            return jsonify({"error": f"source must be one of: {', '.join(VALID_SOURCES)}"}), 400

        file = (await request.files).get("file")
        if not file:
            return jsonify({"error": "file is required"}), 400

        try:
            with _copy_upload_to_spooled_temp(file, max_bytes=_IMPORT_MAX_SIZE) as tmp:
                if is_zip_file(tmp):
                    json_data = extract_json_from_zip_file(tmp)
                else:
                    tmp.seek(0)
                    raw = tmp.read().decode("utf-8")
                    json_data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError,
                zipfile.BadZipFile) as exc:
            return jsonify({"error": f"ファイル読み込みエラー: {exc}"}), 400

        with _import_lock:
            if _import_job and _import_job.running:
                return jsonify({"error": "import already running"}), 409
            _import_job = ImportJob()
            job = _import_job

        def _run():
            try:
                from core.services_core.chatlog_write_service import import_chatlog_payload

                submit_db_write(
                    lambda: import_chatlog_payload(source, json_data, job=job)
                )
            except Exception as exc:
                logger.error("Chatlog import failed: %s", exc)
                job.error = str(exc)
                job.running = False

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        return jsonify({"status": "started"})

    # -- API: import (JSON body + file path, for MCP) --

    @bp.route("/api/import-path", methods=["POST"])
    async def api_import_path():
        global _import_job

        body = await request.get_json(silent=True) or {}
        source = body.get("source", "").strip()
        if source not in VALID_SOURCES:
            return jsonify({"error": f"source must be one of: {', '.join(VALID_SOURCES)}"}), 400

        json_path = body.get("json_path", "").strip()
        if not json_path:
            return jsonify({"error": "json_path is required"}), 400

        # Prevent path traversal
        abs_path = os.path.abspath(json_path)
        if not os.path.isfile(abs_path):
            return jsonify({"error": "file not found"}), 404

        try:
            if abs_path.lower().endswith(".zip"):
                json_data = extract_json_from_zip_path(abs_path)
            else:

                def _load_json(path: str) -> object:
                    # Off the loop: the file is caller-named and unbounded.
                    with open(path, encoding="utf-8") as f:
                        return json.load(f)

                json_data = await asyncio.to_thread(_load_json, abs_path)
        except (OSError, json.JSONDecodeError, ValueError,
                zipfile.BadZipFile) as exc:
            return jsonify({"error": f"ファイル読み込みエラー: {exc}"}), 400

        from core.services_core.chatlog_write_service import import_chatlog_payload

        result = submit_db_write(lambda: import_chatlog_payload(source, json_data))

        return jsonify({
            "status": "completed",
            "added": result.added,
            "skipped": result.skipped,
            "errors": result.errors[:10],
            "total": result.total,
        })

    # -- API: import status --

    @bp.route("/api/import/status")
    async def api_import_status():
        if not _import_job:
            return jsonify({
                "running": False, "phase": "idle",
                "current": 0, "total": 0, "percent": 0,
                "message": "", "error": None,
            })
        return jsonify(_import_job.to_dict())


def extract_json_from_zip(data: bytes) -> Any:
    """Extract and parse JSON from a ZIP archive.

    Prefers conversations.json if present, otherwise uses the first .json file.
    Enforces a size limit to prevent ZIP bombs.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return _extract_json_from_zip_handle(zf)


def extract_json_from_zip_file(file_obj) -> Any:
    """Extract and parse JSON from a ZIP file object."""
    file_obj.seek(0)
    with zipfile.ZipFile(file_obj) as zf:
        return _extract_json_from_zip_handle(zf)


def extract_json_from_zip_path(path: str) -> Any:
    """Extract and parse JSON from a ZIP file path."""
    with zipfile.ZipFile(path) as zf:
        return _extract_json_from_zip_handle(zf)


def _extract_json_from_zip_handle(zf: zipfile.ZipFile) -> Any:
    """Common ZIP-to-JSON extraction logic with member size limits."""
    json_names = [n for n in zf.namelist() if n.lower().endswith(".json")]
    if not json_names:
        raise ValueError("ZIP 内に JSON ファイルが見つかりません")

    # Prefer conversations.json
    target = next(
        (n for n in json_names if os.path.basename(n).lower() == "conversations.json"),
        json_names[0],
    )

    info = zf.getinfo(target)
    if info.file_size > _ZIP_MAX_SIZE:
        raise ValueError(f"展開後サイズが上限超過: {info.file_size:,} bytes")

    raw = zf.read(target).decode("utf-8")
    return json.loads(raw)


def _copy_upload_to_spooled_temp(storage, *, max_bytes: int):
    """Stream an upload into a spooled temp file and enforce a hard size cap."""
    stream = getattr(storage, "stream", storage)
    tmp = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)  # noqa: SIM115 — intentional: file lives beyond context
    total = 0
    while True:
        chunk = stream.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            tmp.close()
            raise ValueError(f"file exceeds {max_bytes:,} byte limit")
        tmp.write(chunk)
    tmp.seek(0)
    return tmp


def is_zip_file(file_obj) -> bool:
    """Detect ZIP format from a file-like object without consuming it."""
    pos = file_obj.tell()
    try:
        return is_zip_bytes(file_obj.read(4))
    finally:
        file_obj.seek(pos)


def is_zip_bytes(data: bytes) -> bool:
    """Detect ZIP format by magic bytes (PK\\x03\\x04)."""
    return data[:4] == b"PK\x03\x04"


def int_param(name: str, default: int, min_val: int = 0, max_val: int = 10000) -> int:
    """Parse an integer query parameter with bounds checking."""
    try:
        val = int(request.args.get(name, default))
        return max(min_val, min(val, max_val))
    except (ValueError, TypeError):
        return default
