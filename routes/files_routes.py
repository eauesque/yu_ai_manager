"""File route handlers for single-file endpoints."""

from quart import request

from core.file_api import build_file_detail_payload, convert_prompt_payload
from core.files_core.original import serve_original
from core.files_core.thumbnail import serve_thumbnail
from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.infra_core.thread_pool import run_in_heavy_io
from core.search_api.utils import SQLITE_MAX_INT, SQLITE_MIN_INT
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope
from routes.files_response import to_flask_response


def _clamp_file_id(file_id: int) -> int:
    # Werkzeug's <int:…> converter accepts arbitrarily large Python ints from
    # the URL path; clamp to SQLite signed-64 range so bind params never overflow.
    return max(SQLITE_MIN_INT, min(SQLITE_MAX_INT, file_id))


async def thumbnail(file_id):
    """Thumbnail API with cache and media support."""
    # Heavy-IO pool, not DB pool: serve_thumbnail spends most of its time on
    # cache disk reads + PIL generation, not on the 1ms DB lookup.
    result = await run_in_heavy_io(serve_thumbnail, _clamp_file_id(file_id))
    return await to_flask_response(result)


async def file_detail(file_id):
    """File detail API."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    payload, status = await run_db_sync(build_file_detail_payload, _clamp_file_id(file_id))
    return api_result(payload, status)


async def convert():
    """Prompt conversion API."""
    data, err = await require_json_dict(request)
    if err:
        return api_result(err[0], err[1])
    payload, status = await run_db_sync(convert_prompt_payload, data)
    return api_result(payload, status)


async def preview(file_id):
    """Mid-resolution preview API (max 1200px).

    Provides a faster-loading intermediate image for the detail modal
    when the original is large.  Falls back to original for video/audio.
    """
    from core.files_core.preview import serve_preview

    result = await run_in_heavy_io(serve_preview, _clamp_file_id(file_id))
    return await to_flask_response(result)


async def original(file_id):
    """Original media API with ZIP support."""
    result = await run_in_heavy_io(serve_original, _clamp_file_id(file_id))
    return await to_flask_response(result, streamable=True)


async def internal_file_detail(file_id):
    """Internal bridge: loopback only. Rust handles auth before forwarding here."""
    from quart import request as _req
    if _req.remote_addr not in ("127.0.0.1", "::1"):
        return api_result({"error": "loopback_only"}, 403)
    payload, status = await run_db_sync(build_file_detail_payload, _clamp_file_id(file_id))
    return api_result(payload, status)
