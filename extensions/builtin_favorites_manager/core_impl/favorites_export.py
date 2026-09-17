"""Framework-free favorites export logic.

Builds ZIP bytes and symlink-folder exports without any Flask dependency,
so the same logic can be reused by a desktop frontend.
"""

import logging
import os
import re
import tempfile
import time
import zipfile
from collections.abc import Iterable

from core.configuration.api import load_config_json
from core.helpers_core.archive_zip_copy import (
    get_archive_member_size,
    write_archive_member_to_zip,
)
from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path
from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE, ARCHIVE_MAX_EXPORT_BYTES
from core.zip_core.zip_path_resolve import is_zip_path

from . import get_collection_name, get_favorite_file_paths

logger = logging.getLogger(__name__)

_SPOOL_MAX_MEMORY = 16 * 1024 * 1024  # 16 MB before spilling ZIP output to disk


def build_export_zip_filename(collection_id: int | None) -> str:
    """Return a descriptive ZIP filename for the given collection.

    The name is sanitised before embedding in the Content-Disposition header to
    prevent header injection via collection names containing CR/LF or quotes.
    """
    raw = get_collection_name(collection_id) or f"collection_{collection_id}" if collection_id else "favorites"
    # Strip characters unsafe in RFC 6266 quoted-string (keep word chars, dash, dot, space)
    cname = re.sub(r'[^\w\-. ]', '_', raw).strip('_').strip() or "favorites"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{cname}_{timestamp}.zip"


def _resolve_export_pairs(
    collection_id: int | None,
    *,
    file_pairs: Iterable[tuple[int, str]] | None = None,
    allowed_file_ids: set[int] | frozenset[int] | None = None,
) -> list[tuple[int, str]]:
    pairs = list(file_pairs) if file_pairs is not None else get_favorite_file_paths(collection_id=collection_id)
    if allowed_file_ids is None:
        return pairs
    return [(fid, path) for fid, path in pairs if fid in allowed_file_ids]


def open_favorites_zip_stream(
    collection_id: int | None,
    *,
    file_pairs: Iterable[tuple[int, str]] | None = None,
    allowed_file_ids: set[int] | frozenset[int] | None = None,
):
    """Build a ZIP into a spooled file and return it positioned at the start."""
    export_pairs = _resolve_export_pairs(
        collection_id,
        file_pairs=file_pairs,
        allowed_file_ids=allowed_file_ids,
    )
    if not export_pairs:
        return None

    buf = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY, mode="w+b")  # noqa: SIM115 — intentional: file lives beyond context
    accumulated = 0
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            used_names: set[str] = set()
            for _fid, path in export_pairs:
                try:
                    if is_archive_member(path):
                        arc_path, internal = split_archive_path(path)
                        entry_size = get_archive_member_size(arc_path, internal)
                        if entry_size > ARCHIVE_MAX_ENTRY_SIZE:
                            logger.warning(
                                "Skipping oversized archive member: %s!%s (%d MB)",
                                arc_path, internal, entry_size // (1024 * 1024),
                            )
                            continue
                        arcname = os.path.basename(internal)
                    elif os.path.isfile(path):
                        entry_size = os.path.getsize(path)
                        if entry_size > ARCHIVE_MAX_ENTRY_SIZE:
                            logger.warning(
                                "Skipping oversized file: %s (%d MB)",
                                path, entry_size // (1024 * 1024),
                            )
                            continue
                        arcname = os.path.basename(path)
                    else:
                        continue

                    if accumulated + entry_size > ARCHIVE_MAX_EXPORT_BYTES:
                        logger.warning(
                            "Favorites ZIP size limit reached at %d MB",
                            accumulated // (1024 * 1024),
                        )
                        break

                    base_name = arcname
                    counter = 2
                    while arcname in used_names:
                        name_part, ext = os.path.splitext(base_name)
                        arcname = f"{name_part}_{counter}{ext}"
                        counter += 1
                    used_names.add(arcname)

                    if is_archive_member(path):
                        write_archive_member_to_zip(zf, arcname, arc_path, internal)
                    else:
                        zf.write(path, arcname)
                    accumulated += entry_size
                except Exception as exc:
                    logger.warning("entry omitted from the export zip: %s", exc)
                    continue
    except Exception:
        buf.close()
        raise

    buf.seek(0)
    return buf


def export_favorites_zip_bytes(collection_id: int | None) -> bytes | None:
    """Build ZIP bytes for favorited files.

    Returns the ZIP bytes, or ``None`` if there are no files to export.
    Aborts if total size exceeds ARCHIVE_MAX_EXPORT_BYTES.
    """
    buf = open_favorites_zip_stream(collection_id)
    if buf is None:
        return None
    try:
        return buf.read()
    finally:
        buf.close()


def _get_allowed_roots() -> list[str]:
    """Return realpath-normalised scan_roots from config."""
    try:
        config = load_config_json(None)
        roots = config.get("scan_roots", [])
        return [os.path.realpath(r["path"]) for r in roots if r.get("path")]
    except Exception:
        return []


def export_favorites_folder(dest_path: str, collection_id: int | None) -> dict:
    """Create symlinks for favorited files in *dest_path*.

    Returns a dict with keys ``ok``, ``created``, ``skipped``, ``errors``,
    ``dest_path``, and optionally ``error``.
    """
    dest_path = dest_path.strip()
    if not dest_path:
        return {"ok": False, "error": "dest_path required"}

    try:
        dest_resolved = os.path.realpath(dest_path)
    except Exception:
        return {"ok": False, "error": "Invalid path"}

    allowed_roots = _get_allowed_roots()
    if not any(
        dest_resolved == root or dest_resolved.startswith(root + os.sep)
        for root in allowed_roots
    ):
        return {"ok": False, "error": "dest_path must be within a configured scan root"}

    try:
        os.makedirs(dest_resolved, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": f"Cannot create directory: {e}"}

    if not os.access(dest_resolved, os.W_OK):
        return {"ok": False, "error": "Directory not writable"}

    file_paths = get_favorite_file_paths(collection_id=collection_id)

    created = 0
    skipped = 0
    errors = 0

    for _fid, path in file_paths:
        try:
            is_zip, _zip_path, _internal = is_zip_path(path)
            if is_zip:
                skipped += 1
                continue

            if not os.path.isfile(path):
                skipped += 1
                continue

            src = os.path.realpath(path)
            basename = os.path.basename(src)
            link_path = os.path.join(dest_resolved, basename)

            counter = 2
            base_link = link_path
            while os.path.exists(link_path):
                name_part, ext = os.path.splitext(os.path.basename(base_link))
                link_path = os.path.join(dest_resolved, f"{name_part}_{counter}{ext}")
                counter += 1

            os.symlink(src, link_path)
            created += 1
        except Exception:
            errors += 1

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "dest_path": dest_resolved,
    }
