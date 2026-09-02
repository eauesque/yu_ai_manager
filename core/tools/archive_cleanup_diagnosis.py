"""Archive pair diagnosis -- detect double extraction, prefix stripping, Unicode normalization.

When archive+folder pair match rate is low, identify the cause and compute an adjusted match rate.
- Double extraction: folder contains a subfolder with same name as archive_stem with matching contents
- Common prefix: all files in archive are under the same directory
- Unicode normalization: cases where NFC/NFD differences cause mismatch
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Any


def diagnose_pair(
    arc_files: list[tuple[str, int]],
    folder_files: list[tuple[str, int]],
    folder_path: str,
    archive_stem: str,
    original_match_rate: float,
) -> dict[str, Any]:
    """Diagnose cause of pair mismatch and return adjusted match ratereturn.

    Returns::

        {
            "diagnosis": "double_extraction" | "prefix_stripped" | "unicode_normalized" | null,
            "adjusted_match_rate": float | null,
            "adjustment_reason": str | null,
        }
    """
    if original_match_rate >= 99.9:
        return {"diagnosis": None, "adjusted_match_rate": None,
                "adjustment_reason": None}

    # 1) Double extraction check
    result = _check_double_extraction(
        arc_files, folder_path, archive_stem)
    if result:
        return result

    # 2) Common prefix removal + Unicode normalization
    result = _check_prefix_and_unicode(arc_files, folder_files)
    if result:
        return result

    # 3) Unicode normalization only
    result = _check_unicode_only(arc_files, folder_files)
    if result:
        return result

    # 4) Estimate identity by file count + size distribution
    result = _check_size_profile(arc_files, folder_files, original_match_rate)
    if result:
        return result

    return {"diagnosis": None, "adjusted_match_rate": None,
            "adjustment_reason": None}


def _check_double_extraction(
    arc_files: list[tuple[str, int]],
    folder_path: str,
    archive_stem: str,
) -> dict[str, Any] | None:
    """Check if folder contains subfolder with same name as archive_stem with matching contents。"""
    sub = Path(folder_path) / archive_stem
    if not sub.is_dir():
        return None

    # Get file list from subfolder
    sub_files: list[tuple[str, int]] = []
    try:
        for root, _dirs, files in os.walk(sub):
            for fname in files:
                fpath = Path(root) / fname
                try:
                    rel = fpath.relative_to(sub)
                    sub_files.append((_norm(str(rel)), fpath.stat().st_size))
                except (OSError, ValueError):
                    pass
    except PermissionError:
        return None

    if not sub_files:
        return None

    # Compare archive files with subfolder files
    match_count = _count_matches(arc_files, sub_files)
    total = max(len(arc_files), len(sub_files), 1)
    rate = round(match_count / total * 100, 1)

    if rate >= 80.0:
        return {
            "diagnosis": "double_extraction",
            "adjusted_match_rate": rate,
            "adjustment_reason":
                f"二重解凍を検出: フォルダー内の '{archive_stem}/' サブフォルダーと"
                f"アーカイブ内容が {rate}% 一致",
        }
    return None


def _check_prefix_and_unicode(
    arc_files: list[tuple[str, int]],
    folder_files: list[tuple[str, int]],
) -> dict[str, Any] | None:
    """Remove archive common prefix and re-compare with Unicode NFC normalization。"""
    prefix = _detect_common_prefix(arc_files)
    if not prefix:
        return None

    # Archive file list with prefix removed
    stripped = [
        (_norm_nfc(name[len(prefix):]), size)
        for name, size in arc_files
    ]
    nfc_folder = [(_norm_nfc(name), size) for name, size in folder_files]

    match_count = _count_matches(stripped, nfc_folder)
    total = max(len(stripped), len(nfc_folder), 1)
    rate = round(match_count / total * 100, 1)

    if rate > 0:
        return {
            "diagnosis": "prefix_stripped",
            "adjusted_match_rate": rate,
            "adjustment_reason":
                f"共通プレフィックス '{prefix}' を除去し Unicode 正規化後に {rate}% 一致",
        }
    return None


def _check_unicode_only(
    arc_files: list[tuple[str, int]],
    folder_files: list[tuple[str, int]],
) -> dict[str, Any] | None:
    """Re-compare with Unicode NFC normalization only。"""
    nfc_arc = [(_norm_nfc(name), size) for name, size in arc_files]
    nfc_folder = [(_norm_nfc(name), size) for name, size in folder_files]

    match_count = _count_matches(nfc_arc, nfc_folder)
    total = max(len(nfc_arc), len(nfc_folder), 1)
    rate = round(match_count / total * 100, 1)

    # Report if there's improvement over the original match rate
    orig_match = _count_matches(arc_files, folder_files)
    if match_count > orig_match:
        return {
            "diagnosis": "unicode_normalized",
            "adjusted_match_rate": rate,
            "adjustment_reason":
                f"Unicode NFC 正規化後に {rate}% 一致 "
                f"(正規化前: {orig_match}/{total} 件)",
        }
    return None


def _check_size_profile(
    arc_files: list[tuple[str, int]],
    folder_files: list[tuple[str, int]],
    original_match_rate: float,
) -> dict[str, Any] | None:
    """When file count matches and size distribution is identical, infer same content。

    Even when name-based match rate drops due to filename encoding
    or prefix differences, file count and individual sizes can
    estimate identity with high confidence。
    """
    if len(arc_files) != len(folder_files) or len(arc_files) == 0:
        return None

    arc_sizes = sorted(s for _, s in arc_files)
    fld_sizes = sorted(s for _, s in folder_files)

    size_match = sum(1 for a, f in zip(arc_sizes, fld_sizes, strict=False) if a == f)
    size_rate = round(size_match / len(arc_sizes) * 100, 1)

    # Report only if size distribution match rate is significantly higher than original
    if size_rate >= 90.0 and size_rate > original_match_rate + 5:
        return {
            "diagnosis": "size_profile_match",
            "adjusted_match_rate": size_rate,
            "adjustment_reason":
                f"ファイル数が一致 ({len(arc_files)} files) かつサイズ分布が"
                f" {size_rate}% 一致 -- ファイル名の差異により元の一致率が"
                f"低下していますが、同一内容の可能性が高いです。"
                f"念のため確認をお勧めします",
        }
    return None


def _detect_common_prefix(files: list[tuple[str, int]]) -> str | None:
    """Detect whether all files are under the same directory and find common prefixreturn."""
    if not files:
        return None

    names = [name for name, _ in files]
    # Only entries containing path separators
    dirs = [name.rsplit("/", 1)[0] + "/" for name in names if "/" in name]
    if len(dirs) != len(names):
        return None  # Top-level files are mixed in

    # Check if all files are under the same directory
    first = dirs[0]
    if all(d == first for d in dirs):
        return first

    # Shortest common prefix (at directory boundary)
    common = os.path.commonprefix(dirs)
    if "/" in common:
        common = common[:common.rfind("/") + 1]
        if common and all(name.startswith(common) for name in names):
            return common

    return None


def _count_matches(
    list_a: list[tuple[str, int]],
    list_b: list[tuple[str, int]],
) -> int:
    """Count matches by filename + size。"""
    set_b = set(list_b)
    return sum(1 for item in list_a if item in set_b)


def _norm(name: str) -> str:
    """Path separator normalization。"""
    return name.replace("\\", "/")


def _norm_nfc(name: str) -> str:
    """Path separator + Unicode NFC normalization。"""
    return unicodedata.normalize("NFC", name.replace("\\", "/"))
