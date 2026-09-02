"""LAN Collection Share — Quart blueprint.

Host-side API (requires PIN auth):
  POST /api/lan-share/create   — create share token
  POST /api/lan-share/revoke   — revoke share token

Guest-side routes (PIN bypass — token is the auth):
  GET  /s/<token>              — collection view page
  GET  /s/<token>/thumb/<id>   — thumbnail proxy
  GET  /s/<token>/download.zip — ZIP download
"""

import logging
from importlib import import_module

from core.lan_share.token_store import (
    create_share_token,
    revoke_token,
    validate_token,
)
from quart import (
    Blueprint,
    Response,
    make_response,
    render_template,
    request,
    send_file,
)

from core.files_core.response_types import FileError, FilePath
from core.files_core.thumbnail import serve_thumbnail
from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict
from core.web.api_rate_limit import get_client_ip
from core.web.public_host import resolve_public_host, resolve_public_port

logger = logging.getLogger(__name__)

bp = Blueprint("lan_share", __name__)


# -------------------------------------------------------------------
# Host-side API (PIN-protected, normal auth flow)
# -------------------------------------------------------------------


@bp.route("/api/lan-share/create", methods=["POST"])
async def api_create_share():
    """Create a LAN share token for a collection."""
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0], err[1])

    collection_id = data.get("collection_id")
    if not collection_id or not isinstance(collection_id, int):
        return api_error("collection_id (int) is required", 400)

    try:
        share = create_share_token(collection_id)
    except ValueError:
        logger.exception("Failed to create LAN share", extra={"collection_id": collection_id})
        return api_error("LAN share could not be created", 400)

    # Build the guest URL using LAN IP
    host = resolve_public_host(get_client_ip())
    port = resolve_public_port()
    url = f"http://{host}:{port}/s/{share.token}"

    return api_success(
        {
            "token": share.token,
            "url": url,
            "expires_in": int(share.expires_at - share.created_at),
            "image_count": len(share.allowed_file_ids),
            "collection_name": share.collection_name,
        },
        201,
    )


@bp.route("/api/lan-share/revoke", methods=["POST"])
async def api_revoke_share():
    """Revoke a LAN share token."""
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0], err[1])

    token = data.get("token", "")
    if not token:
        return api_error("token is required", 400)

    revoke_token(token)
    return api_success({"ok": True}, 200)


# -------------------------------------------------------------------
# Guest-side routes (PIN bypass — token is the only auth)
# -------------------------------------------------------------------


async def _resolve_token(token: str):
    """Validate token and return (share, None) or (None, error_response)."""
    share = validate_token(token)
    if share is None:
        return None, (await render_template("lan_share/collection_share.html", expired=True), 410)
    return share, None


@bp.route("/s/<token>")
async def guest_view(token):
    """Guest collection view page."""
    share, err = await _resolve_token(token)
    if err:
        return err

    file_ids = sorted(share.allowed_file_ids)
    remaining = max(0, int(share.expires_at - __import__("time").time()))

    return await render_template(
        "lan_share/collection_share.html",
        expired=False,
        token=token,
        collection_name=share.collection_name,
        file_ids=file_ids,
        image_count=len(file_ids),
        remaining_seconds=remaining,
    )


@bp.route("/s/<token>/thumb/<int:file_id>")
async def guest_thumbnail(token, file_id):
    """Proxy thumbnail for guest — scoped to allowed_file_ids."""
    share = validate_token(token)
    if share is None:
        return "Token expired", 410

    if file_id not in share.allowed_file_ids:
        return "Forbidden", 403

    result = serve_thumbnail(file_id)

    if isinstance(result, FileError):
        return result.message, result.status_code

    if result.etag:
        if_none_match = request.headers.get("If-None-Match")
        if if_none_match and if_none_match == result.etag:
            resp = await make_response("", 304)
            resp.headers["ETag"] = result.etag
            return resp

    if isinstance(result, FilePath):
        resp = await make_response(await send_file(str(result.path), mimetype=result.mime_type))
    else:
        resp = await make_response(result.data)
        resp.headers["Content-Type"] = result.mime_type

    if result.etag:
        resp.headers["ETag"] = result.etag
    resp.headers["Cache-Control"] = result.cache_control
    return resp


@bp.route("/s/<token>/download.zip")
async def guest_download_zip(token):
    """ZIP download for guest — uses existing export logic."""
    share = validate_token(token)
    if share is None:
        return "Token expired", 410

    try:
        fav_export = import_module(
            "extensions.builtin_favorites_manager.core_impl.favorites_export"
        )
    except ImportError:
        return "Export not available", 503

    zip_file = fav_export.open_favorites_zip_stream(
        share.collection_id,
        allowed_file_ids=share.allowed_file_ids,
    )
    if zip_file is None:
        return "No files to export", 404

    # build filename from collection name
    from core.services_core.lan_share_service import get_collection_zip_filename

    filename = get_collection_zip_filename(share.collection_id)

    def generate():
        try:
            while True:
                chunk = zip_file.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            zip_file.close()

    headers = {
        "Content-Type": "application/zip",
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return Response(generate(), headers=headers)
