"""Share payload builders."""

from pathlib import Path

from core.services_core.db_api import get_readonly_db
from core.share_ops.prompt_extract import extract_share_prompt_data


def build_share_data_payload(file_id: int):
    """Build compact QR share payload for a file."""
    con = get_readonly_db()

    file_row = con.execute(
        "SELECT id, path FROM files WHERE id=? AND is_deleted=0",
        (file_id,),
    ).fetchone()
    if not file_row:
        return {"error": "Not found", "code": "not_found"}, 404

    tmpl = con.execute(
        """
        SELECT file_id, raw_prompt, raw_negative, model_name, raw_meta_json
        FROM templates
        WHERE file_id=?
        """,
        (file_id,),
    ).fetchone()
    if not tmpl:
        return {
            "file_id": file_id,
            "filename": Path(file_row["path"]).name,
            "positive": "",
            "negative": "",
            "model": "",
            "parameters": {},
            "has_metadata": False,
            "message": "この画像にはプロンプトメタデータがありません",
        }, 200

    positive, negative, model, params = extract_share_prompt_data(tmpl)

    share_data = {
        "v": "1.0",
        "t": "prompt",
        "p": positive[:2000],
        "n": negative[:1000],
        "src": "TagDB",
    }
    if model:
        share_data["m"] = model
    if params.get("Seed"):
        share_data["s"] = params["Seed"]
    if params.get("Steps"):
        share_data["st"] = params["Steps"]
    if params.get("CFG scale"):
        share_data["cfg"] = params["CFG scale"]
    if params.get("Sampler"):
        share_data["sa"] = params["Sampler"]
    if params.get("Size"):
        share_data["sz"] = params["Size"]

    return share_data, 200
