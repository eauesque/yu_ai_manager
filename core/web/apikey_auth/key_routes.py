"""API key management endpoints (PIN session required)."""

from __future__ import annotations

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict

from .key_scopes import validate_scopes
from .key_store import create_key, delete_key, list_keys, update_key_label

bp = Blueprint("apikeys_core", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/apikeys", methods=["POST"])
async def api_create_key():
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    label = data.get("label", "")
    if not isinstance(label, str):
        label = ""
    scopes = data.get("scopes")
    if scopes is not None:
        scope_err = validate_scopes(scopes)
        if scope_err:
            return api_error(scope_err, 400)
    result = create_key(label=label, scopes=scopes if scopes else None)
    return api_success(result, 201)


@bp.route("/api/apikeys", methods=["GET"])
async def api_list_keys():
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    keys = list_keys()
    return api_success({"keys": keys})


@bp.route("/api/apikeys/<key_id>", methods=["PATCH"])
async def api_update_key(key_id: str):
    data, err = await require_json_dict(request)
    if err:
        return api_error(err[0]["error"], err[1])
    label = data.get("label")
    if not isinstance(label, str):
        return api_error("label must be a string", 400)
    if update_key_label(key_id, label):
        return api_success({"updated": key_id})
    return api_error("API key not found", 404)


@bp.route("/api/apikeys/<key_id>", methods=["DELETE"])
async def api_delete_key(key_id: str):
    if delete_key(key_id):
        return api_success({"deleted": key_id})
    return api_error("API key not found", 404)
