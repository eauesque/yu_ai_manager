"""Archive cleanup scanning -- detect archive+folder pairs.

Scans directories for ZIP/7z/RAR archives that have a matching
extracted folder, computes file match rates, and builds comparison
pair data.
"""

from __future__ import annotations

import logging
import os
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar")


# ── Scan ─────────────────────────────────────────────────────────

def scan_archive_pairs(
    directory: str,
    recursive: bool = False,
) -> dict[str, Any]:
    """Scan *directory* for archive+folder pairs and compute match rate.

    Returns ``{"pairs": [...], "total_pairs": N}`` on success,
    or ``{"error": "..."}`` on failure.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return {"error": f"Directory not found: {directory}"}

    pairs: list[dict[str, Any]] = []

    if recursive:
        _scan_recursive(dir_path, pairs)
    else:
        _scan_single_dir(dir_path, pairs)

    pairs.sort(key=lambda p: p["archive_name"])
    return {"pairs": pairs, "total_pairs": len(pairs)}


def _scan_single_dir(base: Path, out: list[dict[str, Any]]) -> None:
    """Scan one directory level for archive+folder pairs."""
    try:
        entries = list(base.iterdir())
    except PermissionError:
        return

    archives = [
        e for e in entries
        if e.is_file() and e.suffix.lower() in ARCHIVE_EXTENSIONS
    ]

    for arc in archives:
        folder = base / arc.stem
        if folder.is_dir():
            pair = _build_pair(arc, folder)
            if pair:
                out.append(pair)


def _scan_recursive(base: Path, out: list[dict[str, Any]]) -> None:
    """Walk directory tree and collect archive+folder pairs."""
    visited: set = set()
    for root, _dirs, files in os.walk(base):
        root_path = Path(root)
        for fname in files:
            fpath = root_path / fname
            if fpath.suffix.lower() not in ARCHIVE_EXTENSIONS:
                continue
            folder = root_path / fpath.stem
            if folder.is_dir():
                key = str(fpath)
                if key not in visited:
                    visited.add(key)
                    pair = _build_pair(fpath, folder)
                    if pair:
                        out.append(pair)


def _build_pair(archive: Path, folder: Path) -> dict[str, Any] | None:
    """Build a comparison pair dict for one archive+folder."""
    try:
        arc_files = _list_archive(archive)
    except Exception as exc:
        logger.debug("Cannot read archive %s: %s", archive, exc)
        return None

    folder_files = _list_folder(folder)

    match_count = 0
    for name, size in arc_files:
        for fn, fs in folder_files:
            if fn == name and fs == size:
                match_count += 1
                break

    total = max(len(arc_files), len(folder_files), 1)
    match_rate = round(match_count / total * 100, 1)

    arc_total_size = sum(s for _, s in arc_files)
    folder_total_size = sum(s for _, s in folder_files)

    # Identify mismatch cause with the diagnosis engine
    from core.tools.archive_cleanup_diagnosis import diagnose_pair
    diag = diagnose_pair(
        arc_files, folder_files,
        str(folder), archive.stem, match_rate,
    )

    return {
        "archive_path": str(archive),
        "archive_name": archive.name,
        "archive_ext": archive.suffix.lower(),
        "archive_size": archive.stat().st_size,
        "archive_file_count": len(arc_files),
        "archive_content_size": arc_total_size,
        "folder_path": str(folder),
        "folder_name": folder.name,
        "folder_file_count": len(folder_files),
        "folder_size": folder_total_size,
        "match_count": match_count,
        "match_rate": match_rate,
        "diagnosis": diag["diagnosis"],
        "adjusted_match_rate": diag["adjusted_match_rate"],
        "adjustment_reason": diag["adjustment_reason"],
    }


# ── Archive / folder listing helpers ─────────────────────────────

def _list_archive(archive: Path) -> list[tuple[str, int]]:
    """List (relative_path, size) tuples for files inside an archive."""
    ext = archive.suffix.lower()
    if ext == ".zip":
        return _list_zip(archive)
    if ext == ".7z":
        return _list_7z(archive)
    if ext == ".rar":
        return _list_rar(archive)
    return []


def _list_zip(archive: Path) -> list[tuple[str, int]]:
    with zipfile.ZipFile(archive, "r") as zf:
        result: list[tuple[str, int]] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            filename = _decode_zip_filename(info)
            result.append((_normalize_name(filename), info.file_size))
        return result


def _decode_zip_filename(info: zipfile.ZipInfo) -> str:
    """Decode ZIP entry filename with CJK 10-step fallback chain.

    ZIP spec: flag_bits bit 11 means UTF-8.  Otherwise cp437 encoded,
    but CJK-created ZIPs use various encodings.

    Uses the shared fallback chain from ``core.infra_core.encoding``:
    UTF-8 -> cp932 -> euc-jp -> iso-2022-jp -> euc-kr -> cp949 ->
    gb2312 -> gbk -> big5 -> cp950 -> shift_jis

    See: docs/development/development_docs/ENCODING_FALLBACK.md
    """
    # bit 11 = UTF-8 flag
    if info.flag_bits & 0x800:
        return info.filename  # Python already decoded as UTF-8

    # Non-UTF-8: get raw bytes and re-decode
    try:
        raw = info.filename.encode("cp437")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename

    # Prefer UTF-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # CJK fallback chain (shared with encoding.py)
    from core.infra_core.encoding import try_decode
    decoded, _enc = try_decode(raw, label=info.filename[:30])
    if decoded is not None:
        return decoded

    return info.filename


def _list_7z(archive: Path) -> list[tuple[str, int]]:
    try:
        from core.sevenz_core.sevenz_cli import list_entries, sevenz_available
    except ImportError:
        logger.debug("sevenz_cli not available -- skipping .7z: %s", archive)
        return []

    if not sevenz_available():
        logger.debug("7z CLI not found -- skipping .7z: %s", archive)
        return []

    return [
        (_normalize_name(entry.filename), entry.size)
        for entry in list_entries(str(archive))
        if not entry.is_directory
    ]


def _list_rar(archive: Path) -> list[tuple[str, int]]:
    try:
        import rarfile  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("rarfile not installed -- skipping .rar: %s", archive)
        return []

    with rarfile.RarFile(archive, "r") as rf:
        return [
            (_normalize_name(info.filename), info.file_size)
            for info in rf.infolist()
            if not info.is_dir()
        ]


def _list_folder(folder: Path) -> list[tuple[str, int]]:
    """List (relative_path, size) tuples for files inside a folder."""
    result: list[tuple[str, int]] = []
    try:
        for root, _dirs, files in os.walk(folder):
            for fname in files:
                fpath = Path(root) / fname
                try:
                    rel = fpath.relative_to(folder)
                    result.append((_normalize_name(str(rel)), fpath.stat().st_size))
                except (OSError, ValueError):
                    pass
    except PermissionError:
        pass
    return result


def _normalize_name(name: str) -> str:
    """Normalize path separators and Unicode NFC for comparison."""
    return unicodedata.normalize("NFC", name.replace("\\", "/"))
