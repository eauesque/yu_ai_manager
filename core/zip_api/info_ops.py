"""Info/open-folder operations for ZIP file routes."""

import os

from core.platform import open_in_file_manager
from core.services_core.db_api import get_readonly_db


def get_file_info_payload(file_id: int):
    """Return file info including ZIP extraction metadata."""
    con = get_readonly_db()
    row = con.execute(
        """
        SELECT path, is_zip_member, extracted_from_zip,
               extracted_from_internal, extraction_date, extracted_to_file_id
        FROM files WHERE id=?
        """,
        (file_id,),
    ).fetchone()
    if not row:
        return {"error": "File not found", "code": "file_not_found"}, 404

    return {
        "path": row["path"],
        "is_zip_member": bool(row["is_zip_member"]),
        "extracted_from_zip": row["extracted_from_zip"],
        "extracted_from_internal": row["extracted_from_internal"],
        "extraction_date": row["extraction_date"],
        "extracted_to_file_id": row["extracted_to_file_id"],
    }, 200


def open_folder_for_file(file_id: int):
    """Open file parent folder in platform file manager."""
    con = get_readonly_db()
    row = con.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return {"error": "File not found", "code": "file_not_found"}, 404

    path = row["path"]
    if "!" in path:
        path = path.split("!")[0]
    dir_path = os.path.dirname(os.path.abspath(path))

    open_in_file_manager(path)
    return {"success": True, "path": dir_path}, 200
