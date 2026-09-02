"""Drag & drop file registration service.

Handles two related operations:

1. **Upload + register** — an uploaded multipart file is saved into the
   configured drop inbox (which must live inside an existing scan root) and
   then ingested via :func:`core.scan_core.scanner.scan_one`.

2. **Register by path** — an existing filesystem path is registered directly,
   used by the MCP ``register_file`` tool and any other headless caller. The
   path must already live inside one of the configured scan roots.
"""

from __future__ import annotations

import os
import sqlite3 as _sqlite3
from pathlib import Path
from typing import Any

from core.scan_core.scanner import scan_one
from core.schema_core.schema import connect_db
from core.services_core.db_state import get_db_path
from core.services_core.db_write import submit_db_write

_ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif", ".svg",
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v",
}


def _enabled_scan_roots(config: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    for entry in config.get("scan_roots", []) or []:
        if not isinstance(entry, dict):
            continue
        if not entry.get("enabled", True):
            continue
        raw = entry.get("path")
        if not raw:
            continue
        try:
            roots.append(Path(raw).expanduser().resolve())
        except OSError:
            continue
    return roots


def resolve_drop_inbox_dir(
    config: dict[str, Any],
) -> tuple[Path | None, str | None]:
    """Return ``(resolved_path, error_message)``.

    The resolved path is either ``config["drop_inbox_dir"]`` (when set and
    inside a scan root) or the first enabled scan root (fallback). Returns
    ``(None, error)`` when no valid inbox can be determined.
    """
    roots = _enabled_scan_roots(config)
    if not roots:
        return None, "no scan roots configured"

    explicit = config.get("drop_inbox_dir")
    if explicit:
        try:
            candidate = Path(str(explicit)).expanduser().resolve()
        except OSError as exc:
            return None, f"invalid drop_inbox_dir: {exc}"
        for root in roots:
            try:
                candidate.relative_to(root)
                return candidate, None
            except ValueError:
                continue
        return None, (
            f"drop_inbox_dir {str(explicit)!r} is not inside any configured scan root"
        )

    return roots[0], None


def _sanitize_upload_name(raw: str) -> str:
    normalized = (raw or "").strip().replace("\\", "/")
    base = os.path.basename(normalized)
    if not base or base in (".", ".."):
        return ""
    base = base.replace("\x00", "").replace("/", "_").replace("\\", "_")
    return base


def _pick_unique_target(inbox: Path, name: str) -> Path:
    p = Path(name)
    stem, suffix = p.stem, p.suffix
    target = inbox / name
    idx = 1
    while target.exists():
        target = inbox / f"{stem}_{idx}{suffix}"
        idx += 1
        if idx > 9999:
            raise OSError("could not pick unique filename after 9999 attempts")
    return target


def _path_is_inside_scan_root(path: Path, config: dict[str, Any]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    for root in _enabled_scan_roots(config):
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _ingest_path_sync(target: Path, config: dict[str, Any]):
    """Run scan_one() against the writable library DB on the single-writer thread."""

    def _do():
        con = connect_db(str(get_db_path()))
        try:
            con.row_factory = _sqlite3.Row
            result = scan_one(con, target, config, force=True, compute_hash=True)
            con.commit()
            return result
        finally:
            con.close()

    return submit_db_write(_do)


def _format_result_entry(target: Path, result, extra: dict | None = None) -> dict:
    entry: dict[str, Any] = {
        "ok": True,
        "path": str(target),
        "filename": target.name,
    }
    if result is None:
        entry["status"] = "skipped"
    else:
        action, file_id = result
        entry["status"] = action
        entry["file_id"] = file_id
    if extra:
        entry.update(extra)
    return entry


def ingest_upload_payload(
    uploaded_file, config: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Save an uploaded multipart file to the inbox and register it.

    Returns ``(payload, http_status)``.
    """
    inbox, err = resolve_drop_inbox_dir(config)
    if err or inbox is None:
        return {"ok": False, "code": "no_inbox", "error": err or "inbox unresolved"}, 400

    name = _sanitize_upload_name(getattr(uploaded_file, "filename", "") or "")
    if not name:
        return {"ok": False, "code": "invalid_filename", "error": "invalid filename"}, 400

    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        return {
            "ok": False,
            "code": "unsupported_type",
            "error": f"unsupported extension: {ext or '(none)'}",
            "filename": name,
        }, 400

    try:
        inbox.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "code": "inbox_unwritable",
            "error": f"cannot create inbox dir: {exc}",
        }, 500

    try:
        target = _pick_unique_target(inbox, name)
    except OSError as exc:
        return {"ok": False, "code": "name_collision", "error": str(exc)}, 500

    try:
        uploaded_file.save(str(target))
    except Exception as exc:
        return {
            "ok": False,
            "code": "save_failed",
            "error": f"failed to save upload: {exc}",
        }, 500

    try:
        result = _ingest_path_sync(target, config)
    except Exception as exc:
        return {
            "ok": False,
            "code": "scan_failed",
            "error": f"scan failed: {exc}",
            "path": str(target),
            "filename": target.name,
        }, 500

    return _format_result_entry(target, result), 200


def ingest_upload_batch_payload(
    uploaded_files: list, config: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Register many uploaded files and return a batch payload."""
    if not uploaded_files:
        return {"ok": False, "code": "no_files", "error": "no files uploaded"}, 400

    results: list[dict[str, Any]] = []
    success = 0
    for f in uploaded_files:
        entry, _status = ingest_upload_payload(f, config)
        results.append(entry)
        if entry.get("ok"):
            success += 1

    return {
        "ok": success > 0,
        "total": len(results),
        "success": success,
        "results": results,
    }, 200


def register_path_payload(
    raw_path: str, config: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Register an on-disk file path that already lives inside a scan root."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return {"ok": False, "code": "invalid_path", "error": "path must be a non-empty string"}, 400

    try:
        target = Path(raw_path).expanduser().resolve()
    except OSError as exc:
        return {"ok": False, "code": "invalid_path", "error": str(exc)}, 400

    if not target.exists() or not target.is_file():
        return {"ok": False, "code": "not_found", "error": f"file not found: {target}"}, 404

    if not _path_is_inside_scan_root(target, config):
        return {
            "ok": False,
            "code": "outside_scan_root",
            "error": "path is not inside any configured scan root",
        }, 400

    ext = target.suffix.lower()
    if ext not in _ALLOWED_EXTS:
        return {
            "ok": False,
            "code": "unsupported_type",
            "error": f"unsupported extension: {ext or '(none)'}",
            "path": str(target),
            "filename": target.name,
        }, 400

    try:
        result = _ingest_path_sync(target, config)
    except Exception as exc:
        return {
            "ok": False,
            "code": "scan_failed",
            "error": f"scan failed: {exc}",
            "path": str(target),
            "filename": target.name,
        }, 500

    return _format_result_entry(target, result), 200
