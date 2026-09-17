"""File-import route for Prompt Library API."""

from __future__ import annotations

import os
from collections.abc import Callable

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .prompt_library_write import create_prompt


def _extract_novelai_characters(detail: dict) -> list | None:
    novelai_v4 = detail.get("novelai_v4_data")
    if not novelai_v4:
        return None
    characters = []
    char_prompts = novelai_v4.get("character_prompts") or []
    neg_chars = novelai_v4.get("negative_characters") or []
    for index, prompt in enumerate(char_prompts):
        if not isinstance(prompt, dict):
            continue
        entry = {"prompt": prompt.get("prompt") or "", "negative": "", "center": None}
        positions = prompt.get("positions") or []
        if positions and isinstance(positions[0], dict):
            entry["center"] = {"x": positions[0].get("x", 0.5), "y": positions[0].get("y", 0.5)}
        if index < len(neg_chars):
            neg = neg_chars[index]
            entry["negative"] = (neg.get("prompt") or "") if isinstance(neg, dict) else ""
        characters.append(entry)
    return characters


def register_from_file_routes(
    bp: Blueprint,
    require_admin_scope: Callable[[], object | None] | None = None,
) -> None:
    @bp.route("/api/prompts/from-file", methods=["POST"])
    async def api_from_file():
        if require_admin_scope:
            auth_err = require_admin_scope()
            if auth_err:
                return auth_err
        data, err = await require_json_dict(request)
        if err:
            return api_error(err[0]["error"], err[1])
        file_id = data.get("file_id")
        if not file_id:
            return api_error("file_id is required", 400, code="missing_file_id")

        from core.prompt.detail_parsing import resolve_detail_fields
        from core.services_core.db_api import get_db as get_db_conn

        con = get_db_conn()
        row = con.execute(
            "SELECT f.id, f.path, f.meta_source, tm.raw_prompt, tm.raw_negative, tm.raw_meta_json, tm.model_name "
            "FROM files f LEFT JOIN templates tm ON tm.file_id=f.id WHERE f.id=? AND f.is_deleted=0",
            (file_id,),
        ).fetchone()
        if not row:
            return api_error("File not found", 404, code="file_not_found")

        detail = resolve_detail_fields({
            "meta_source": row[2],
            "raw_prompt": row[3] or "",
            "raw_negative": row[4] or "",
            "raw_meta_json": row[5],
            "model_name": row[6],
        })
        params = detail.get("parameters") or {}
        title = data.get("title", "").strip() or os.path.splitext(os.path.basename(row[1] or ""))[0][:80] or "Imported"

        item = create_prompt(
            title=title,
            positive=detail.get("positive") or "",
            negative=detail.get("negative") or "",
            seed=str(params.get("Seed") or ""),
            steps=str(params.get("Steps") or ""),
            sampler=str(params.get("Sampler") or ""),
            cfg_scale=str(params.get("CFG scale") or ""),
            model_name=detail.get("model") or "",
            memo=data.get("memo", ""),
            source_file_id=file_id,
            characters=_extract_novelai_characters(detail),
        )
        return api_success({"prompt": item}, 201)
