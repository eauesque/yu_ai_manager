"""Ratings API routes (Pydantic validated)."""

from importlib import import_module

from pydantic import Field
from quart import Blueprint

from core.infra_core.api_errors import api_result
from core.infra_core.api_models import ApiModel, FileId, FileIdsParam, Rating
from core.infra_core.api_validate import validate_request
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# Import from relocated ratings extension
_ratings_mod = import_module("extensions.builtin_ratings.core_impl")
get_rating = _ratings_mod.get_rating
get_rating_stats = _ratings_mod.get_rating_stats
get_ratings_batch = _ratings_mod.get_ratings_batch
set_rating = _ratings_mod.set_rating
set_ratings_batch = _ratings_mod.set_ratings_batch

bp = Blueprint("ratings", __name__)

_BATCH_SET_MAX = 500


class SetRatingRequest(ApiModel):
    """Rating set request."""
    file_id: FileId
    rating: Rating


class BatchSetItem(ApiModel):
    """Individual item for batch set."""
    file_id: FileId
    rating: Rating


class BatchSetRequest(ApiModel):
    """Rating batch set request."""
    items: list[BatchSetItem] = Field(min_length=1, max_length=_BATCH_SET_MAX)


class GetRatingRequest(ApiModel):
    """Rating get request."""
    file_id: FileId


@bp.route("/api/ratings/set", methods=["POST"])
@validate_request(SetRatingRequest)
async def api_ratings_set(*, data: SetRatingRequest):
    result = await run_db_sync(set_rating, data.file_id, data.rating)
    return api_result(result, 200)


@bp.route("/api/ratings/get")
@validate_request(GetRatingRequest)
async def api_ratings_get(*, data: GetRatingRequest):
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    rating = await run_db_sync(get_rating, data.file_id)
    return api_result({"file_id": data.file_id, "rating": rating}, 200)


@bp.route("/api/ratings/batch", methods=["POST"])
@validate_request(FileIdsParam)
async def api_ratings_batch(*, data: FileIdsParam):
    ratings = await run_db_sync(get_ratings_batch, data.file_ids)
    return api_result({"ratings": ratings}, 200)


@bp.route("/api/ratings/batch-set", methods=["POST"])
@validate_request(BatchSetRequest)
async def api_ratings_batch_set(*, data: BatchSetRequest):
    items = [{"file_id": item.file_id, "rating": item.rating} for item in data.items]
    result = await run_db_sync(set_ratings_batch, items)
    return api_result({"data": result}, 200)


@bp.route("/api/ratings/stats")
async def api_ratings_stats():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    stats = await run_db_sync(get_rating_stats)
    return api_result(stats, 200)
