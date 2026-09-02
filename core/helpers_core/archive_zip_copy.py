"""Archive-member helpers for streaming into output ZIP files."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from shutil import copyfileobj


def get_archive_member_size(archive_path: str, internal_path: str) -> int:
    """Return the uncompressed size of an archive member."""
    lower = archive_path.lower()
    if lower.endswith(".7z"):
        from core.sevenz_core.sevenz_support_core import get_size_from_7z

        return get_size_from_7z(archive_path, internal_path)
    if lower.endswith(".rar"):
        from core.rar_core.rar_support_core import get_size_from_rar

        return get_size_from_rar(archive_path, internal_path)
    from core.zip_core.zip_support_core import get_size_from_zip

    return get_size_from_zip(archive_path, internal_path)


def write_archive_member_to_zip(
    output_zf: zipfile.ZipFile,
    arcname: str,
    archive_path: str,
    internal_path: str,
) -> None:
    """Copy an archive member into an output ZIP without materializing bytes."""
    lower = archive_path.lower()
    if lower.endswith(".7z"):
        _write_7z_member_to_zip(output_zf, arcname, archive_path, internal_path)
        return
    if lower.endswith(".rar"):
        _write_rar_member_to_zip(output_zf, arcname, archive_path, internal_path)
        return
    _write_zip_member_to_zip(output_zf, arcname, archive_path, internal_path)


def _write_zip_member_to_zip(
    output_zf: zipfile.ZipFile, arcname: str, archive_path: str, internal_path: str
) -> None:
    from core.zip_core.zip_path_resolve import _resolve_entry_name

    with zipfile.ZipFile(archive_path, "r") as src_zf:
        resolved = _resolve_entry_name(src_zf, internal_path)
        with src_zf.open(resolved) as src, output_zf.open(arcname, "w") as dst:
            copyfileobj(src, dst, length=1024 * 1024)


def _write_rar_member_to_zip(
    output_zf: zipfile.ZipFile, arcname: str, archive_path: str, internal_path: str
) -> None:
    import rarfile

    from core.rar_core.rar_support_core import _resolve_entry_name

    with rarfile.RarFile(archive_path, "r") as rf:
        resolved = _resolve_entry_name(rf.namelist(), internal_path)
        with rf.open(resolved) as src, output_zf.open(arcname, "w") as dst:
            copyfileobj(src, dst, length=1024 * 1024)


def _write_7z_member_to_zip(
    output_zf: zipfile.ZipFile, arcname: str, archive_path: str, internal_path: str
) -> None:
    from core.sevenz_core import sevenz_cli
    from core.sevenz_core.sevenz_support_core import _resolve_entry_name

    resolved = _resolve_entry_name(sevenz_cli.list_names(archive_path), internal_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        sevenz_cli.extract_to_dir(archive_path, tmpdir, targets=[resolved])
        extracted = Path(tmpdir, *resolved.split("/"))
        if not extracted.exists():
            raise KeyError(f"Failed to extract entry: {internal_path!r}")
        with extracted.open("rb") as src, output_zf.open(arcname, "w") as dst:
            copyfileobj(src, dst, length=1024 * 1024)
