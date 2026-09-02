"""Temporary extracted paths for archive members."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from shutil import copyfileobj

from .helpers_text_path import is_archive_member, split_archive_path


def _enforce_plain_size_cap(path: str, max_size_bytes: int) -> None:
    """Raise ValueError if a plain file exceeds the configured byte cap."""
    size = os.path.getsize(path)
    if size > max_size_bytes:
        raise ValueError(
            f"Image too large: {path} "
            f"({size / 1024 / 1024:.0f} MB > "
            f"{max_size_bytes / 1024 / 1024:.0f} MB limit)"
        )


@contextmanager
def extracted_zip_member_path(
    archive_path: str,
    internal_path: str,
    *,
    max_size_bytes: int | None = None,
):
    """Yield a temporary extracted path for a ZIP member."""
    import zipfile

    from core.zip_core.zip_path_resolve import _resolve_entry_name

    with zipfile.ZipFile(archive_path, "r") as zf:
        resolved = _resolve_entry_name(zf, internal_path)
        info = zf.getinfo(resolved)
        if max_size_bytes is not None and info.file_size > max_size_bytes:
            raise ValueError(
                f"Entry too large: {internal_path} "
                f"({info.file_size / 1024 / 1024:.0f} MB > "
                f"{max_size_bytes / 1024 / 1024:.0f} MB limit)"
            )
        suffix = Path(resolved).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            with zf.open(resolved) as src:
                copyfileobj(src, tmp, length=1024 * 1024)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


@contextmanager
def extracted_7z_member_path(archive_path: str, internal_path: str):
    """Yield a temporary extracted path for a 7z member."""
    from core.sevenz_core import sevenz_cli
    from core.sevenz_core.sevenz_support_core import _resolve_entry_name

    resolved = _resolve_entry_name(sevenz_cli.list_names(archive_path), internal_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        sevenz_cli.extract_to_dir(archive_path, tmpdir, targets=[resolved])
        extracted = Path(tmpdir, *resolved.split("/"))
        if not extracted.exists():
            raise FileNotFoundError(resolved)
        yield extracted


@contextmanager
def extracted_rar_member_path(archive_path: str, internal_path: str):
    """Yield a temporary extracted path for a RAR member."""
    import rarfile

    from core.rar_core.rar_support_core import _resolve_entry_name

    with rarfile.RarFile(archive_path, "r") as rf:
        resolved = _resolve_entry_name(rf.namelist(), internal_path)
        suffix = Path(resolved).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            with rf.open(resolved) as src:
                copyfileobj(src, tmp, length=1024 * 1024)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


@contextmanager
def extracted_archive_member_path(
    path: str,
    *,
    max_size_bytes: int | None = None,
):
    """Yield a real filesystem path for ``path``, archive member or not.

    Dispatches by the archive extension in the virtual path:
      - ``X.zip!entry`` -> extract via zipfile into a NamedTemporaryFile
      - ``X.7z!entry``  -> extract via sevenz_cli into a TemporaryDirectory
      - ``X.rar!entry`` -> extract via rarfile into a NamedTemporaryFile

    Plain (non-archive) paths are yielded as-is without extraction so the
    caller can use the same ``with extracted_archive_member_path(p) as fp``
    idiom for every code path. This is the helper that should be used by
    any tagger / detector / preprocess pipeline that takes an image path
    from the DB — those paths transparently include archive members.

    ``max_size_bytes``: if set, enforces a size cap on plain files
    (matches the existing yolo / clip_search behaviour). Archive members
    are not pre-checked here because the underlying zip/7z/rar readers
    each apply their own ``max_size`` enforcement when called via
    ``read_archive_member_bytes``; the temp-extract path streams via
    ``copyfileobj`` and trusts the caller's storage.
    """
    if not is_archive_member(path):
        if max_size_bytes is not None:
            _enforce_plain_size_cap(path, max_size_bytes)
        yield path
        return

    archive_path, inner_path = split_archive_path(path)
    lower = archive_path.lower()
    if lower.endswith(".7z"):
        with extracted_7z_member_path(archive_path, inner_path) as fp:
            yield str(fp)
    elif lower.endswith(".rar"):
        with extracted_rar_member_path(archive_path, inner_path) as fp:
            yield str(fp)
    else:
        with extracted_zip_member_path(archive_path, inner_path) as fp:
            yield str(fp)


def read_archive_member_bytes(path: str, *, max_size_bytes: int) -> bytes:
    """Read raw bytes from a plain file or archive member.

    Mirrors the shape that ``builtin_hailo_yolo_detect._read_image_bytes``
    and ``builtin_clip_search.image_io.read_image_bytes`` were doing
    independently: the per-archive readers (``read_bytes_from_zip`` /
    ``_from_7z`` / ``_from_rar``) each support ``max_size``, while plain
    paths get a pre-read ``os.path.getsize`` check.
    """
    if not is_archive_member(path):
        _enforce_plain_size_cap(path, max_size_bytes)
        with open(path, "rb") as f:
            return f.read()

    archive_path, inner_path = split_archive_path(path)
    lower = archive_path.lower()
    if lower.endswith(".7z"):
        from core.sevenz_core.sevenz_support_core import read_bytes_from_7z
        return read_bytes_from_7z(archive_path, inner_path, max_size=max_size_bytes)
    if lower.endswith(".rar"):
        from core.rar_core.rar_support_core import read_bytes_from_rar
        return read_bytes_from_rar(archive_path, inner_path, max_size=max_size_bytes)
    from core.zip_core.zip_support_core import read_bytes_from_zip
    return read_bytes_from_zip(archive_path, inner_path, max_size=max_size_bytes)
