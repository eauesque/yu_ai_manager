"""Container member operations for archive (ZIP/7z/RAR) container view."""

import re

from core.services_core.db_api import get_readonly_db

_ARCHIVE_EXTS = (".zip", ".7z", ".rar")


def _resolve_zip_container_path(path_value: str) -> str:
    path_s = str(path_value or "")
    if "!" in path_s:
        from core.helpers_core.helpers_text_path import archive_part
        return archive_part(path_s)
    if path_s.lower().endswith(_ARCHIVE_EXTS):
        return path_s
    return ""


def _member_name_for_sort(path_value: str) -> str:
    path_s = str(path_value or "")
    if "!" in path_s:
        return path_s.split("!", 1)[1]
    return path_s


def _natural_sort_key(path_value: str):
    name = _member_name_for_sort(path_value).replace("\\", "/")
    parts = re.split(r"(\d+)", name)
    key = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def get_container_members_payload(file_id: int):
    """Return ZIP container members and representative ids for a file."""
    con = get_readonly_db()
    row = con.execute("SELECT id, path FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return {"error": "File not found", "code": "file_not_found"}, 404

    container_path = _resolve_zip_container_path(row["path"])
    if not container_path:
        return {"error": "Container not found for file", "code": "container_not_found"}, 400

    members = list(
        con.execute(
            """
            SELECT id, path
            FROM files
            WHERE is_deleted=0
              AND path LIKE ?
            ORDER BY path
            """,
            (f"{container_path}!%",),
        )
    )

    members_sorted = sorted(
        members,
        key=lambda m: (_natural_sort_key(m["path"]), _member_name_for_sort(m["path"]).lower()),
    )
    member_ids = [int(m["id"]) for m in members_sorted]
    representatives = member_ids[:4]
    focus_id = int(row["id"]) if int(row["id"]) in member_ids else (member_ids[0] if member_ids else None)

    return {
        "success": True,
        "container_path": container_path,
        "member_count": len(member_ids),
        "member_ids": member_ids,
        "representatives": representatives,
        "focus_id": focus_id,
    }, 200
