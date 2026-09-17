"""Input resolution helpers for Speech-to-Text batch transcription."""

import csv
import os

_MEDIA_EXTS = {
    ".webm",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".m4v",
    ".ogv",
    ".mp3",
    ".wav",
    ".ogg",
    ".opus",
    ".m4a",
    ".aac",
    ".flac",
}

_IN_CHUNK_SIZE = 500


def resolve_directory(directory: str, recursive: bool) -> dict:
    """Scan a directory for media files and return matching DB file_ids."""
    if not os.path.isdir(directory):
        return {"error": f"ディレクトリが見つかりません: {directory}", "file_ids": [], "files_found": 0}

    media_paths = _collect_media_paths(directory, recursive)
    if not media_paths:
        return {"error": None, "file_ids": [], "files_found": 0}

    from core.services_core.db_api import get_readonly_db

    con = get_readonly_db()
    normalized = {os.path.normpath(os.path.abspath(path)): True for path in media_paths}
    dir_prefix = os.path.normpath(os.path.abspath(directory))
    if recursive:
        row_iter = con.execute(
            "SELECT id, path FROM files WHERE path LIKE ? AND is_deleted=0",
            (dir_prefix + "%",),
        )
    else:
        row_iter = con.execute(
            "SELECT id, path FROM files WHERE path LIKE ? AND path NOT LIKE ? AND is_deleted=0",
            (dir_prefix + "/%", dir_prefix + "/%/%"),
        )

    file_ids = [row[0] for row in row_iter if os.path.normpath(row[1]) in normalized]
    return {"error": None, "file_ids": file_ids, "files_found": len(media_paths)}


def _collect_media_paths(directory: str, recursive: bool) -> list[str]:
    media_paths: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in _MEDIA_EXTS:
                    media_paths.append(os.path.join(root, fname))
        return media_paths

    for fname in os.listdir(directory):
        path = os.path.join(directory, fname)
        if os.path.isfile(path) and os.path.splitext(fname)[1].lower() in _MEDIA_EXTS:
            media_paths.append(path)
    return media_paths


def resolve_list_file(list_file: str) -> dict:
    """Read file paths from a text/CSV file and return matching DB file_ids."""
    if not os.path.isfile(list_file):
        return {"error": f"リストファイルが見つかりません: {list_file}", "file_ids": [], "lines_read": 0}

    try:
        paths = _read_paths_from_list_file(list_file)
    except Exception as exc:
        return {"error": f"リストファイルの読み込みに失敗: {exc}", "file_ids": [], "lines_read": 0}

    if not paths:
        return {"error": None, "file_ids": [], "lines_read": 0}

    from core.services_core.db_api import get_readonly_db

    con = get_readonly_db()
    norm_list = list({os.path.normpath(os.path.abspath(path)): True for path in paths}.keys())
    file_ids = _match_exact_paths(con, norm_list)
    if not file_ids and norm_list:
        file_ids = _fallback_match_normalized_paths(con, norm_list)
    return {"error": None, "file_ids": file_ids, "lines_read": len(paths)}


def _read_paths_from_list_file(list_file: str) -> list[str]:
    paths: list[str] = []
    ext = os.path.splitext(list_file)[1].lower()
    with open(list_file, encoding="utf-8") as handle:
        if ext == ".csv":
            reader = csv.reader(handle)
            for row_data in reader:
                if row_data:
                    _append_path_if_present(paths, row_data[0])
            return paths

        for line in handle:
            _append_path_if_present(paths, line)
    return paths


def _append_path_if_present(paths: list[str], raw: str) -> None:
    path = raw.strip()
    if path and not path.startswith("#"):
        paths.append(path)


def _match_exact_paths(con, norm_list: list[str]) -> list[int]:
    file_ids: list[int] = []
    for index in range(0, len(norm_list), _IN_CHUNK_SIZE):
        chunk = norm_list[index : index + _IN_CHUNK_SIZE]
        placeholders = ",".join("?" * len(chunk))
        file_ids.extend(row[0] for row in con.execute(
            f"SELECT id, path FROM files WHERE path IN ({placeholders}) AND is_deleted=0",
            chunk,
        ))
    return file_ids


def _fallback_match_normalized_paths(con, norm_list: list[str]) -> list[int]:
    found_ids = set()
    for normalized_path in norm_list:
        row = con.execute(
            "SELECT id FROM files WHERE path=? AND is_deleted=0",
            (normalized_path,),
        ).fetchone()
        if row:
            found_ids.add(row[0])
    return list(found_ids)
