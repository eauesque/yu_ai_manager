"""Path and IO helpers for ZIP handling."""

import datetime as _dt
import logging
import os
import unicodedata
import zipfile

logger = logging.getLogger(__name__)


def _normalize_separators(path: str) -> str:
    return str(path or "").replace("\\", "/").lstrip("./")


def _repair_cp437_name(name: str) -> str | None:
    try:
        return name.encode("cp437").decode("cp932")
    except Exception:
        return None


def _name_variants(name: str) -> list[str]:
    base = _normalize_separators(name)
    variants = {base}
    variants.add(unicodedata.normalize("NFC", base))
    variants.add(unicodedata.normalize("NFKC", base))
    repaired = _repair_cp437_name(base)
    if repaired:
        repaired_norm = _normalize_separators(repaired)
        variants.add(repaired_norm)
        variants.add(unicodedata.normalize("NFC", repaired_norm))
        variants.add(unicodedata.normalize("NFKC", repaired_norm))
    return [v for v in variants if v]


def _resolve_entry_name(zf: zipfile.ZipFile, internal_path: str) -> str:
    names = zf.namelist()
    if internal_path in names:
        return internal_path

    variant_to_actual = {}
    for actual in names:
        for variant in _name_variants(actual):
            variant_to_actual.setdefault(variant, actual)

    for variant in _name_variants(internal_path):
        resolved = variant_to_actual.get(variant)
        if resolved is not None:
            return resolved

    target_name = os.path.basename(_normalize_separators(internal_path))
    if target_name:
        candidates = [n for n in names if os.path.basename(_normalize_separators(n)) == target_name]
        if len(candidates) == 1:
            return candidates[0]

    raise KeyError(internal_path)


def is_zip_path(path: str) -> tuple[bool, str | None, str | None]:
    from core.helpers_core.helpers_text_path import split_archive_path
    if "!" not in path:
        return (False, None, None)
    zip_path, internal_path = split_archive_path(path)
    if os.path.exists(zip_path) and zipfile.is_zipfile(zip_path):
        return (True, zip_path, internal_path)
    return (False, None, None)


def read_bytes_from_zip(zip_path: str, internal_path: str) -> bytes:
    with zipfile.ZipFile(zip_path, "r") as zf:
        resolved = _resolve_entry_name(zf, internal_path)
        return zf.read(resolved)


def get_mtime_from_zip(zip_path: str, internal_path: str) -> int:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            resolved = _resolve_entry_name(zf, internal_path)
            info = zf.getinfo(resolved)
            dt = _dt.datetime(*info.date_time)  # noqa: DTZ001 -- archive entry timestamps are local wall clock, no zone
            return int(dt.timestamp())
    except Exception:
        return int(os.path.getmtime(zip_path))


def get_size_from_zip(zip_path: str, internal_path: str) -> int:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            resolved = _resolve_entry_name(zf, internal_path)
            info = zf.getinfo(resolved)
            return info.file_size
    except Exception:
        return 0


def list_images_in_zip(zip_path: str, extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".svg")) -> list[str]:
    images = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                if name.lower().endswith(extensions):
                    images.append(name)
    except Exception as e:
        logger.warning(f"Failed to list ZIP contents: {zip_path}: {e}")
    return images
