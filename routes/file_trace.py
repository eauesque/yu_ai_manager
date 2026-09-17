"""GET /api/files/<file_id>/analysis-trace — analysis engine trace retrieval."""

from quart import Blueprint

from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_async import run_db_sync
from core.services_core.db_state import get_readonly_db

bp = Blueprint("file_trace", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _build_trace(con, file_id: int) -> dict | None:
    row = con.execute(
        "SELECT meta_source FROM files WHERE id=? AND is_deleted=0", (file_id,)
    ).fetchone()
    if row is None:
        return None

    meta_source = row[0] or "unknown"
    engines = []

    # WD Tagger entries
    wd_rows = con.execute(
        "SELECT md.model, COUNT(*) as tag_count, MAX(fwt.created_at) as last_at "
        "FROM file_wd_tags fwt JOIN wd_model_dict md ON md.id=fwt.model_id "
        "WHERE fwt.file_id=? GROUP BY fwt.model_id ORDER BY md.model",
        (file_id,),
    )
    for r in wd_rows:
        engines.append({
            "engine": "wd_tagger",
            "model": r[0],
            "tag_count": r[1],
            "analyzed_at": r[2],
            "source": "file_wd_tags",
        })

    # Hailo Tagger entries
    hailo_rows = con.execute(
        "SELECT source, COUNT(*) as tag_count, MAX(created_at) as last_at "
        "FROM file_hailo_tags WHERE file_id=? GROUP BY source ORDER BY source",
        (file_id,),
    )
    for r in hailo_rows:
        engines.append({
            "engine": "hailo_tagger",
            "source_label": r[0],
            "tag_count": r[1],
            "analyzed_at": r[2],
            "source": "file_hailo_tags",
        })

    # Generic analysis table
    analysis_rows = con.execute(
        "SELECT engine, quality_score, analyzed_at FROM analysis WHERE file_id=? ORDER BY id",
        (file_id,),
    )
    for r in analysis_rows:
        engines.append({
            "engine": r[0],
            "quality_score": r[1],
            "analyzed_at": r[2],
            "source": "analysis",
        })

    # Sort by analyzed_at descending (newest first)
    engines.sort(key=lambda e: e.get("analyzed_at") or 0, reverse=True)

    return {"meta_source": meta_source, "engines": engines}


@bp.route("/api/files/<int:file_id>/analysis-trace")
async def api_file_analysis_trace(file_id: int):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    def _fetch() -> dict | None:
        con = get_readonly_db()
        return _build_trace(con, file_id)

    result = await run_db_sync(_fetch)
    if result is None:
        return api_error(f"file_id={file_id} が見つかりません", 404)
    return api_success(result)
