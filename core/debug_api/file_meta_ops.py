"""file-meta payload helpers for debug routes."""


from core.services_core.db_api import get_readonly_db
from core.zip_core.zip_support_extract import extract_metadata_from_zip


def file_meta_payload(file_id: int) -> tuple[dict, int]:
    """Build payload for /api/debug/file-meta/<id>."""
    con = get_readonly_db()
    row = con.execute(
        "SELECT f.id, f.path, f.meta_source, f.parser_version, "
        "tm.raw_prompt, tm.raw_negative, tm.raw_meta_json, tm.model_name, tm.format "
        "FROM files f LEFT JOIN templates tm ON f.id=tm.file_id "
        "WHERE f.id=?",
        (file_id,),
    ).fetchone()

    if not row:
        return {"error": "file not found", "code": "file_not_found"}, 404

    raw_meta = row["raw_meta_json"] or ""
    result = {
        "id": row["id"],
        "path": row["path"],
        "meta_source": row["meta_source"],
        "parser_version": row["parser_version"],
        "format": row["format"],
        "model_name": row["model_name"],
        "raw_prompt_length": len(row["raw_prompt"] or ""),
        "raw_prompt_preview": (row["raw_prompt"] or "")[:300],
        "raw_negative_preview": (row["raw_negative"] or "")[:300],
        "raw_meta_json_length": len(raw_meta),
        "raw_meta_json_preview": raw_meta[:500],
        "has_v4_prompt": "v4_prompt" in raw_meta if raw_meta else False,
        "has_comment": "Comment" in raw_meta if raw_meta else False,
    }

    if "!" in row["path"]:
        zip_path, internal = row["path"].split("!", 1)
        try:
            fresh = extract_metadata_from_zip(zip_path, internal)
            result["fresh_extract"] = {
                "meta_source": fresh.get("meta_source"),
                "format": fresh.get("format"),
                "raw_meta_json_length": len(fresh.get("raw_meta_json") or ""),
                "raw_meta_json_preview": (fresh.get("raw_meta_json") or "")[:500],
                "has_v4_prompt": "v4_prompt" in (fresh.get("raw_meta_json") or ""),
                "success": fresh.get("success"),
                "raw_prompt_preview": (fresh.get("raw_prompt") or "")[:200],
            }
        except Exception as exc:
            result["fresh_extract_error"] = str(exc)

    return result, 200
