"""Uploaded-file inspection service for tools routes."""

import contextlib
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.helpers_core.archive_member_temp import extracted_zip_member_path
from core.scan_core.scanner import scan_one
from core.schema_core.schema_init import init_db
from core.services_core.db_cipher import apply_key, sqlite3
from core.services_core.db_state_functions import register_custom_functions
from core.tools.helpers import extract_raw_metadata
from core.zip_core.zip_support_core import list_images_in_zip

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_MAX_INSPECT_IMAGE_BYTES = 50 * 1024 * 1024   # 50 MB (normal images)
_MAX_INSPECT_ZIP_BYTES = 200 * 1024 * 1024    # 200 MB (ZIP uploads)

# Serialize concurrent inspect requests so the global _tag_cache
# snapshot/reset/restore in _inspect_image_file is not interleaved.
# Without this lock, a parallel inspect could reset the cache mid-scan
# of another inspect, re-introducing FK violations from stale tag_ids.
_INSPECT_LOCK = threading.Lock()

# See tmp/inspect_config_audit.md (Task 0.1): scan_one does not consume any
# config keys on the per-file path. If a future scan-time path adds a
# metadata-affecting key, add it here AND extend the parity test
# (tests/test_inspect_modal_parity.py) with stub-vs-real comparison.
_INSPECT_CONFIG: dict[str, Any] = {}


def _make_memory_con() -> sqlite3.Connection:
    """Open an in-memory SQLCipher connection with all required setup.

    Bypasses connect_db() to avoid _ensure_db_migrated() which requires
    DB_PATH to be initialized (only available in the full app runtime).
    """
    con = sqlite3.connect(":memory:", timeout=10.0)
    apply_key(con)
    register_custom_functions(con)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def _apply_inspect_metadata(
    payload: dict[str, Any],
    filename: str,
    size_bytes: int | None,
    raw_metadata: dict[str, Any],
    tmp_path: str,
) -> None:
    """Inject inspect-only fields into the unified payload (rev2 N5).

    Centralises every key that inspect adds on top of build_file_detail_payload
    so that the override surface is visible in one place.

    parsed=True only when scan_one found a known format. When meta_source is
    "unknown" (e.g. corrupt file or unrecognised format) the file row exists
    but no AI metadata was extracted, so we treat it as unparseable.
    """
    payload["filename"] = filename
    payload["raw_metadata"] = raw_metadata
    payload["size"] = size_bytes if size_bytes is not None else os.path.getsize(tmp_path)
    payload["parsed"] = payload.get("meta_source") not in (None, "unknown")


def _inspect_image_file(
    tmp_path: str,
    filename: str,
    ext: str,
    *,
    size_bytes: int | None = None,
) -> tuple[dict, int]:
    """Analyze image metadata from an on-disk path via unified pipeline.

    Opens an in-memory SQLite DB, runs scan_one to populate it, then
    delegates to build_file_detail_payload for the same payload shape as
    the modal detail view.
    """
    con = None
    # Tag cache snapshot/restore (rev2 followup).
    # _tag_cache is module-global. The main app populates it during real
    # scans of the on-disk DB. If we run scan_one against this isolated
    # :memory: con without isolating the cache, upsert_tag returns cached
    # tag_ids that don't exist in the :memory: tags table → FK violation
    # at insert_file_tags_batch. Snapshot + reset + restore around the
    # inspect scan keeps the main cache intact for subsequent real scans.
    from core.models_core import models_tags as _models_tags
    _INSPECT_LOCK.acquire()
    saved_tag_cache = dict(_models_tags._tag_cache)
    _models_tags.reset_tag_cache()
    try:
        raw_metadata = extract_raw_metadata(tmp_path, ext)

        con = _make_memory_con()
        con.row_factory = sqlite3.Row
        init_db(con, enable_fts=False)

        scan_one(con, Path(tmp_path), _INSPECT_CONFIG, force=True, compute_hash=False)

        row = con.execute("SELECT id FROM files LIMIT 1").fetchone()
        if row is None:
            return {
                "filename": filename,
                "parsed": False,
                "raw_metadata": raw_metadata,
            }, 200

        file_id = row["id"]

        from core.file_api.detail_payload import build_file_detail_payload
        # skip_deferred_writes: inspect's :memory: file_id would otherwise
        # resolve to a production row id and overwrite live raw_meta_json.
        payload, status = build_file_detail_payload(file_id, con=con, skip_deferred_writes=True)

        if status != 200:
            return payload, status

        _apply_inspect_metadata(payload, filename, size_bytes, raw_metadata, tmp_path)
        return payload, 200

    except Exception:
        logger.exception("Image inspection failed for %s (ext=%s)", filename, ext)
        return {"error": "Image inspection failed"}, 500
    finally:
        with contextlib.suppress(Exception):
            if con is not None:
                con.close()
        # Restore main-app tag cache so subsequent real scans keep their
        # warm hits. Done in finally so an inspect failure cannot leak the
        # :memory: tag_ids into the main cache.
        _models_tags.reset_tag_cache()
        _models_tags._tag_cache.update(saved_tag_cache)
        _INSPECT_LOCK.release()


def _inspect_image_bytes(
    image_bytes: bytes, filename: str, ext: str
) -> tuple[dict, int]:
    """Write to a temporary file and analyze image metadata."""
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        return _inspect_image_file(tmp_path, filename, ext, size_bytes=len(image_bytes))
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def inspect_uploaded_file(
    file_storage, zip_entry: str = ""
) -> tuple[dict, int]:
    """Save the uploaded file temporarily and return metadata analysis results.

    For ZIP files, returns the internal image list and analyzes the specified entry.
    """
    if file_storage is None:
        return {"error": "No file uploaded"}, 400
    if not file_storage.filename:
        return {"error": "Empty filename"}, 400

    ext = os.path.splitext(file_storage.filename)[1].lower()

    # --- ZIP handling ---
    if ext == ".zip":
        # Validate zip_entry safety
        if zip_entry and ("\x00" in zip_entry or ".." in zip_entry.split("/")):
            return {"error": "Invalid zip entry path"}, 400

        # NOTE: do NOT call file_storage.save() while a NamedTemporaryFile handle
        # is still open — on Windows the open handle blocks the second writer and
        # leaves a 0-byte file. mkstemp returns a path we can fully release first.
        fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            file_storage.save(tmp_zip)
            if os.path.getsize(tmp_zip) > _MAX_INSPECT_ZIP_BYTES:
                return {"error": "Uploaded ZIP is too large (max 200 MB)"}, 400
            images = list_images_in_zip(tmp_zip)
            if not images:
                return {"error": "No image files found in ZIP"}, 400

            target = zip_entry if zip_entry and zip_entry in images else images[0]
            target_ext = os.path.splitext(target)[1].lower()
            with extracted_zip_member_path(
                tmp_zip,
                target,
                max_size_bytes=_MAX_INSPECT_IMAGE_BYTES,
            ) as extracted:
                result, status = _inspect_image_file(
                    str(extracted),
                    f"{file_storage.filename}!{target}",
                    target_ext,
                )
            if status == 200:
                result["zip_images"] = images
                result["zip_current"] = target
            return result, status
        except Exception:
            return {"error": "ZIP inspection failed"}, 500
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_zip)

    # --- Normal image handling ---
    if ext not in _IMAGE_EXTENSIONS:
        return {
            "error": f"Unsupported file type: {ext!r}. "
                     f"Allowed: {', '.join(_IMAGE_EXTENSIONS)}"
        }, 400

    # Read directly from the upload stream to avoid the Windows file-handle race
    # that occurs when calling file_storage.save() while a NamedTemporaryFile is
    # still open on the same path (results in a 0-byte file → PIL "cannot
    # identify image file" for all formats).
    try:
        stream = getattr(file_storage, "stream", None)
        if stream is not None:
            with contextlib.suppress(OSError, AttributeError):
                stream.seek(0)
            image_bytes = stream.read()
        else:
            image_bytes = file_storage.read()
    except Exception:
        return {"error": "Failed to read uploaded file"}, 400

    if not image_bytes:
        return {"error": "Uploaded file is empty"}, 400

    if len(image_bytes) > _MAX_INSPECT_IMAGE_BYTES:
        return {"error": "Uploaded file is too large (max 50 MB)"}, 400

    return _inspect_image_bytes(image_bytes, file_storage.filename, ext)
