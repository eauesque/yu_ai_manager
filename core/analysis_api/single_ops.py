"""Single-file analysis operations."""

import logging
from pathlib import Path

import ai_analysis
from core.analysis_api.engine_resolver import (  # noqa: F401 -- re-exported
    _is_engine_local,
    _is_hailo_vlm_available,
    _is_ollama_available,
    _is_openai_compat_available,
    _resolve_override,
    _resolve_with_fallback,
)
from core.analysis_api.media_extraction import (
    _analyze_archive_image,
    _analyze_one_in_subprocess,
    _analyze_video,
)
from core.configuration.api import load_config_json
from core.helpers_core.helpers_text_path import is_archive_member
from core.services_core.db_api import get_readonly_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)


def analyze_one_file(
    file_id: int,
    mode: str = "full",
    engine_override: str | None = None,
    model_override: str | None = None,
    server_id: str | None = None,
):
    """Analyze a single file with AI engine, returning result dict and status code."""
    config = load_config_json(None)
    ai_config = config.get("ai_analysis", {})

    if engine_override:
        # Verify the specified engine (and model) is configured, use as-is
        engine_type, engine_kwargs, err = _resolve_override(
            ai_config, engine_override, model_override,
        )
    else:
        engine_type, engine_kwargs, err = _resolve_with_fallback(ai_config, server_id=server_id)
    if err:
        return {"error": err}, 400

    ro_con = get_readonly_db()
    row = ro_con.execute("SELECT f.path, f.id FROM files f WHERE f.id=? AND f.is_deleted=0", (file_id,)).fetchone()
    if not row:
        return {"error": "File not found"}, 404
    file_path_str = row["path"]
    archive = is_archive_member(file_path_str)

    # Validate file exists
    if archive:
        from core.helpers_core.helpers_text_path import split_archive_path
        arc_path, _inner = split_archive_path(file_path_str)
        if not Path(arc_path).exists():
            return {"error": "Archive file does not exist on disk"}, 404
    else:
        if not Path(file_path_str).exists():
            return {"error": "File does not exist on disk"}, 404

    # Hailo VLM holds the GIL during NPU inference, so run in a separate process
    if engine_type == "hailo_vlm":
        return _analyze_one_in_subprocess(file_id, file_path_str, config)

    tags_rows = ro_con.execute(
        "SELECT t.tag FROM tags t JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.file_id=?",
        (file_id,),
    )
    existing_tags = [r[0] for r in tags_rows]
    tmpl = ro_con.execute("SELECT raw_prompt FROM templates WHERE file_id=?", (file_id,)).fetchone()
    existing_prompt = tmpl["raw_prompt"] if tmpl else None

    engine = ai_analysis.get_engine(engine_type, **engine_kwargs)

    from core.files_core.media_types import is_video_file

    try:
        if is_video_file(file_path_str):
            result = _analyze_video(
                engine, file_path_str, existing_tags, existing_prompt,
                config, archive,
            )
        elif archive:
            result = _analyze_archive_image(
                engine, file_path_str, existing_tags, existing_prompt,
            )
        else:
            result = engine.analyze_image(
                Path(file_path_str), existing_tags, existing_prompt, mode=mode,
            )
    except RuntimeError as exc:
        logger.warning("analysis.analyze engine error for file_id=%s: %s", file_id, exc)
        return {"error": str(exc)}, 200

    # Include mode name in engine identifier to allow multiple results to coexist
    engine_label = engine.get_name()
    if mode != "full":
        engine_label += f" [{mode}]"
    def _write() -> None:
        from core.services_core.db_api import get_db
        con = get_db()
        ai_analysis.save_analysis(con, file_id, engine_label, result)

    submit_db_write(_write)
    return {"success": True, "result": result.to_dict(), "engine": engine_label}, 200


def get_analysis_result(file_id: int):
    """Retrieve stored analysis results for a file."""
    from core.services_core.db_api import get_readonly_db
    con = get_readonly_db()
    # Return all results (supports multiple engines/modes)
    all_results = ai_analysis.get_all_analyses(con, file_id)
    if not all_results:
        return {"found": False}, 200
    return {"found": True, "result": all_results[0], "results": all_results}, 200
