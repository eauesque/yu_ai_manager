"""Builder for folder/archive group indexes."""

from __future__ import annotations

import re

_ARCHIVE_MEMBER_RE = re.compile(r"^.+\.(?:zip|7z|rar)!.+$", re.IGNORECASE)
_ARCHIVE_EXT_RE = re.compile(r"\.(?:zip|7z|rar)$", re.IGNORECASE)
_NATURAL_RE = re.compile(r"(\d+)")
_BATCH_SIZE = 50000


def natural_sort_key(path: str):
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    parts = _NATURAL_RE.split(name)
    key = []
    for p in parts:
        key.append((0, int(p), "") if p.isdigit() else (1, 0, p.lower()))
    return key


def db_signature(db):
    row = db.execute(
        "SELECT COUNT(*), MAX(mtime) FROM files WHERE is_deleted = 0"
    ).fetchone()
    return (row[0] or 0, row[1] or 0)


def build_groups_index(db, cache_version: int) -> dict:
    file_count = 0
    max_mtime = 0
    folder_groups: dict[str, list[int]] = {}
    archive_groups: dict[str, list[int]] = {}
    folder_meta: dict[str, tuple[str, int]] = {}
    archive_meta: dict[str, tuple[str, int]] = {}

    last_id = 0
    while True:
        cursor = db.execute(
            "SELECT id, path, mtime FROM files "
            "WHERE is_deleted=0 AND id > ? ORDER BY id LIMIT ?",
            (last_id, _BATCH_SIZE),
        )
        batch_count = 0
        for row in cursor:
            batch_count += 1
            fid, path, mtime = row[0], row[1] or "", row[2] or 0
            file_count += 1
            max_mtime = max(max_mtime, mtime)
            if _ARCHIVE_MEMBER_RE.match(path):
                from core.helpers_core.helpers_text_path import archive_part

                _append_group("archive:" + archive_part(path).lower(), archive_groups, archive_meta, fid, path, mtime)
            elif _ARCHIVE_EXT_RE.search(path):
                _append_group("archive:" + path.lower(), archive_groups, archive_meta, fid, path, mtime)
            else:
                norm = path.replace("\\", "/")
                idx = norm.rfind("/")
                dirname_lower = norm[:idx].lower() if idx > 0 else "."
                _append_group("folder:" + dirname_lower, folder_groups, folder_meta, fid, path, mtime)
            last_id = fid
        if batch_count < _BATCH_SIZE:
            break

    return {
        "file_count": file_count,
        "max_mtime": max_mtime,
        "cache_version": cache_version,
        "folders": _build_entries(folder_groups, folder_meta, 2),
        "zips": _build_entries(archive_groups, archive_meta, 1),
    }


def _append_group(
    key: str,
    groups: dict[str, list[int]],
    meta_map: dict[str, tuple[str, int]],
    fid: int,
    path: str,
    mtime: int,
) -> None:
    groups.setdefault(key, []).append(fid)
    prev = meta_map.get(key)
    if prev is None:
        meta_map[key] = (path, mtime)
    elif mtime > prev[1]:
        meta_map[key] = (prev[0], mtime)


def _build_entries(groups: dict[str, list[int]], meta_map: dict[str, tuple[str, int]], min_members: int) -> dict:
    out = {}
    for key, ids in groups.items():
        if len(ids) < min_members:
            continue
        meta = meta_map[key]
        out[key] = {
            "ids": ids,
            "label": _group_label(key, meta[0]),
            "reps": ids[:8],
            "max_mtime": meta[1],
        }
    return out


def _dirname(path: str) -> str:
    norm = path.replace("\\", "/")
    idx = norm.rfind("/")
    return norm[:idx] if idx > 0 else "."


def _basename(path: str) -> str:
    norm = path.replace("\\", "/")
    idx = norm.rfind("/")
    return norm[idx + 1:] if idx >= 0 else norm


def _container_path(path: str) -> str:
    if _ARCHIVE_MEMBER_RE.match(path):
        from core.helpers_core.helpers_text_path import archive_part

        return archive_part(path)
    if _ARCHIVE_EXT_RE.search(path):
        return path
    return ""


def _group_label(key: str, first_path: str) -> str:
    if key.startswith("archive:"):
        return _basename(_container_path(first_path) or first_path)
    if key.startswith("folder:"):
        d = _dirname(first_path)
        parts = d.replace("\\", "/").split("/")
        return parts[-1] if parts[-1] else d
    return _basename(first_path)
