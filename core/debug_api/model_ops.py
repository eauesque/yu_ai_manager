"""model-check payload helpers for debug routes."""

from core.services_core.db_api import get_readonly_db


def model_check_payload():
    """Build payload for model_name debug status."""
    con = get_readonly_db()
    with_model = con.execute(
        "SELECT COUNT(*) FROM templates WHERE model_name IS NOT NULL AND model_name != ''"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM templates").fetchone()[0]

    samples_with = con.execute(
        "SELECT file_id, model_name, model_hash, format FROM templates WHERE model_name IS NOT NULL AND model_name != '' ORDER BY file_id LIMIT 10"
    )
    samples_without = con.execute(
        "SELECT file_id, model_name, format, raw_meta_json FROM templates WHERE (model_name IS NULL OR model_name = '') ORDER BY file_id LIMIT 5"
    )

    return {
        "total_templates": total,
        "with_model_name": with_model,
        "without_model_name": total - with_model,
        "samples_with_model": [
            {"file_id": r[0], "model_name": r[1], "model_hash": r[2], "format": r[3]}
            for r in samples_with
        ],
        "samples_without_model": [
            {
                "file_id": r[0],
                "model_name": r[1],
                "format": r[2],
                "raw_meta_json_preview": (r[3] or "")[:200],
            }
            for r in samples_without
        ],
    }
