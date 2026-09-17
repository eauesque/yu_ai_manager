"""SNS Share API routes -- X Intent URL + Bluesky post + config.

Bluesky notification queue / monitor config routes live in
core/sns_share_api/bsky_queue.py and are wired up via add_url_rule below.
"""

from importlib import import_module

from pydantic import Field
from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_models import ApiModel, FileId
from core.infra_core.api_validate import validate_request
from core.services_core.db_async import run_db_sync
from core.sns_share_api import bsky_queue as _bq

bp = Blueprint("sns_share", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# -- Request Models ----------------------------------------------------------

class BlueskyPostRequest(ApiModel):
    """Bluesky post request."""
    file_id: FileId
    text: str | None = Field(default=None, max_length=1000)
    attach_image: bool = True


class SnsConfigRequest(ApiModel):
    """SNS config save request."""
    bluesky_handle: str = Field(default="", max_length=200)
    bluesky_app_password: str = Field(default="", max_length=200)
    post_template: str = Field(default="", max_length=2000)


# -- Preview & X Intent (GET, unlimited) -------------------------------------

@bp.route("/api/sns/preview")
async def api_sns_preview():
    """Template expansion preview + grapheme count."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    file_id = request.args.get("file_id", type=int)
    template = request.args.get("template", default=None, type=str)
    if not file_id:
        return api_error("file_id is required", 400)

    _pb = import_module("extensions.builtin_sns_share.core_impl.post_builder")
    result = await run_db_sync(_pb.build_post_text, file_id, template)
    if result.get("error"):
        return api_error(result["error"], 404)
    return api_result(result, 200)


@bp.route("/api/sns/x/intent")
async def api_sns_x_intent():
    """Return X (Twitter) Web Intent URL."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    file_id = request.args.get("file_id", type=int)
    if not file_id:
        return api_error("file_id is required", 400)

    _pb = import_module("extensions.builtin_sns_share.core_impl.post_builder")
    url = await run_db_sync(_pb.build_x_intent_url, file_id)
    return api_result({"url": url}, 200)


# -- Bluesky (POST, HEAVY tier via path classification) ----------------------

@bp.route("/api/sns/bluesky/post", methods=["POST"])
@validate_request(BlueskyPostRequest)
async def api_sns_bluesky_post(*, data: BlueskyPostRequest):
    """Post to Bluesky."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _bsky = import_module("extensions.builtin_sns_share.core_impl.bluesky_client")
    result = await run_db_sync(_bsky.post_to_bluesky, data.file_id, data.text, data.attach_image)
    if not result["ok"]:
        if "インストール" in (result.get("error") or ""):
            return api_error(result["error"], 501)
        return api_error(result["error"], 400)
    return api_result(result, 200)


@bp.route("/api/sns/bluesky/test", methods=["POST"])
async def api_sns_bluesky_test():
    """Bluesky connection test."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _bsky = import_module("extensions.builtin_sns_share.core_impl.bluesky_client")
    result = await run_db_sync(_bsky.test_connection)
    if not result["ok"]:
        if "インストール" in (result.get("error") or ""):
            return api_error(result["error"], 501)
        return api_error(result["error"], 400)
    return api_result(result, 200)


# -- Config (GET unlimited, POST DESTRUCTIVE tier) ---------------------------

@bp.route("/api/sns/config")
async def api_sns_config_get():
    """Get SNS settings (passwords masked)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _cred = import_module("extensions.builtin_sns_share.core_impl.credential_store")
    return api_result(await run_db_sync(_cred.get_masked_config), 200)


@bp.route("/api/sns/config", methods=["POST"])
@validate_request(SnsConfigRequest)
async def api_sns_config_save(*, data: SnsConfigRequest):
    """Save SNS settings."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    _cred = import_module("extensions.builtin_sns_share.core_impl.credential_store")
    _sess = import_module("extensions.builtin_sns_share.core_impl.bluesky_session")

    def _save(handle, app_password, post_template):
        sns = _cred.load_sns_config()
        sns["bluesky"]["handle"] = handle
        if app_password and "****" not in app_password:
            sns["bluesky"]["app_password"] = app_password
        if post_template:
            sns["post_template"] = post_template
        _cred.save_sns_config(sns)
        _sess.clear_session()

    await run_db_sync(_save, data.bluesky_handle, data.bluesky_app_password, data.post_template)

    return api_result({"saved": True}, 200)


# -- Bluesky Notification Queue (delegated to core/sns_share_api/bsky_queue.py) --

bp.add_url_rule("/api/sns/bsky/queue", view_func=_bq.bsky_queue)
bp.add_url_rule("/api/sns/bsky/queue/pending", view_func=_bq.bsky_pending)
bp.add_url_rule("/api/sns/bsky/queue/<int:queue_id>/triage", view_func=_bq.bsky_triage, methods=["POST"])
bp.add_url_rule("/api/sns/bsky/queue/<int:queue_id>/status", view_func=_bq.bsky_status, methods=["PUT"])
bp.add_url_rule("/api/sns/bsky/queue/<int:queue_id>/respond", view_func=_bq.bsky_respond, methods=["POST"])
bp.add_url_rule("/api/sns/bsky/monitor/config", endpoint="api_bsky_monitor_config_get", view_func=_bq.bsky_monitor_config_get)
bp.add_url_rule("/api/sns/bsky/monitor/config", endpoint="api_bsky_monitor_config_save", view_func=_bq.bsky_monitor_config_save, methods=["PUT"])
bp.add_url_rule("/api/sns/bsky/monitor/triage-prompts", endpoint="api_bsky_triage_prompts_get", view_func=_bq.bsky_triage_prompts_get)
bp.add_url_rule("/api/sns/bsky/monitor/triage-prompts", endpoint="api_bsky_triage_prompts_save", view_func=_bq.bsky_triage_prompts_save, methods=["PUT"])
bp.add_url_rule("/api/sns/bsky/queue/poll", view_func=_bq.bsky_poll, methods=["POST"])
