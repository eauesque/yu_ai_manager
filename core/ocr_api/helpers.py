"""OCR API common helpers."""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path


@contextlib.contextmanager
def resolve_image_path(file_path_str: str):
    """Resolve actual image path from a DB path string.

    For files inside ZIP/7z archives (``archive.zip!entry.png``), extracts to
    a temporary file that is auto-deleted on context exit. Regular files are
    returned as-is.

    Yields:
        (Path, error_string) -- error_string is empty on success.
    """
    from core.helpers_core.helpers_text_path import (
        is_archive_member,
        split_archive_path,
    )

    if is_archive_member(file_path_str):
        arc_path, inner = split_archive_path(file_path_str)
        if not Path(arc_path).exists():
            yield None, "Archive file not found on disk"
            return
        suffix = Path(inner).suffix or ".jpg"
        try:
            if arc_path.lower().endswith(".7z"):
                from core.sevenz_core.sevenz_support_core import read_bytes_from_7z
                img_bytes = read_bytes_from_7z(arc_path, inner)
            elif arc_path.lower().endswith(".rar"):
                from core.rar_core.rar_support_core import read_bytes_from_rar
                img_bytes = read_bytes_from_rar(arc_path, inner)
            else:
                from core.zip_core.zip_support_core import read_bytes_from_zip
                img_bytes = read_bytes_from_zip(arc_path, inner)
        except Exception as exc:
            yield None, f"Failed to extract from archive: {exc}"
            return
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = Path(tmp.name)
        try:
            yield tmp_path, ""
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        p = Path(file_path_str)
        if not p.exists():
            yield None, "Image file not found on disk"
            return
        yield p, ""


def load_translations_for_export(con, file_id, target_lang=""):
    """Convert translation data to export-ready dictionaries.

    Returns:
        (region_translations: {region_id: text}, translated_full_text: str)
    """
    from core.ocr_core.translation import get_translations_for_file

    trans_rows = get_translations_for_file(con, file_id)
    region_trans = {}
    full_text = ""

    for tr in trans_rows:
        if target_lang and tr.get("target_lang") != target_lang:
            continue
        if not full_text and tr.get("translated_text"):
            full_text = tr["translated_text"]
        for rt in tr.get("region_translations", []):
            rid = rt.get("region_id")
            if rid is not None and rt.get("translated"):
                region_trans[rid] = rt["translated"]

    return (region_trans or None, full_text)
