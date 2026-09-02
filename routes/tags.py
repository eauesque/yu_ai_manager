"""Tags batch API routes."""

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.tags_core import set_tags_batch
from core.tags_core.store import search_tags

bp = Blueprint("tags", __name__)

_BATCH_SET_MAX = 500


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/tags/batch-set", methods=["POST"])
async def api_tags_batch_set():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON object required", 400, code="invalid_json")

    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return api_error("items array required", 400, code="batch_empty")
    if len(items) > _BATCH_SET_MAX:
        return api_error(
            f"Batch size {len(items)} exceeds maximum of {_BATCH_SET_MAX}",
            400,
            code="batch_too_large",
        )

    result = await run_db_sync(set_tags_batch, items, source="user")
    return api_result({"data": result}, 200)


@bp.route("/api/tags/dedup", methods=["POST"])
async def api_tags_dedup():
    data = await request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("JSON object required", 400, code="invalid_json")
    tags_raw = data.get("tags")
    keep_last = data.get("keep") == "last"
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        return api_error("tags is required (string or array)", 400, code="invalid_value")
    seen: set[str] = set()
    if keep_last:
        deduped = [t for t in reversed(tags) if (t.lower() not in seen) and not seen.add(t.lower())]  # type: ignore[func-returns-value]
        deduped.reverse()
    else:
        deduped = [t for t in tags if (t.lower() not in seen) and not seen.add(t.lower())]  # type: ignore[func-returns-value]
    return api_result({"tags": deduped, "string": ", ".join(deduped), "removed": len(tags) - len(deduped)})


@bp.route("/api/tags/suggest")
async def api_tags_suggest():
    """Return tag suggestions for autocomplete."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    q = request.args.get("q", "").strip()
    if not q:
        return api_result({"data": []}, 200)
    limit = min(int(request.args.get("limit", "20")), 100)
    tags = await run_db_sync(search_tags, q, limit=limit)
    return api_result({"data": tags}, 200)
