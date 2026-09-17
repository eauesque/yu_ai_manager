"""GET /api/workflow-gen-params/<file_id> — retrieve _gen_params backup."""
from __future__ import annotations

import asyncio
from pathlib import Path

from quart import Blueprint

from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_api import get_readonly_db

bp = Blueprint("workflow_params", __name__)


@bp.route("/api/workflow-gen-params/<int:file_id>", methods=["GET"])
async def api_workflow_gen_params(file_id: int):
    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0", (file_id,)
    ).fetchone()
    if not row:
        return api_error("no gen params backup for this file", 404)

    file_path = Path(row[0])
    if not file_path.is_file():
        return api_error("no gen params backup for this file", 404)

    def _read() -> dict | None:
        from extensions.builtin_comfyui_bridge.core_impl.comfyui_image_workflow import (
            extract_gen_params_from_image,
        )

        return extract_gen_params_from_image(file_path.read_bytes(), file_path.name)

    gen_params = await asyncio.to_thread(_read)
    if not gen_params:
        return api_error("no gen params backup for this file", 404)

    result = dict(gen_params)
    result["hint"] = (
        "This JSON contains the generation parameters used to create this image. "
        "Pass it directly to an LLM to reconstruct a ComfyUI workflow."
    )
    return api_success(result)
