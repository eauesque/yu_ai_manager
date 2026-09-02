"""Route registration for archive cleanup APIs."""

from quart import request

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.services_core.db_async import run_db_sync
from core.tools_api.archive_cleanup_ops import (
    execute_archive_cleanup_payload,
    get_ac_llm_config_payload,
    list_models_payload,
    llm_verify_batch_payload,
    llm_verify_payload,
    save_ac_llm_config_payload,
    scan_archive_pairs_payload,
)
from core.web.auth_helpers import require_local as _require_local


def register_tools_archive_cleanup_routes(bp):
    """Register archive cleanup related tool routes."""

    @bp.route("/api/tools/archive-cleanup/scan", methods=["POST"])
    async def api_tools_archive_cleanup_scan():
        blocked = _require_local("Archive cleanup scan")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(scan_archive_pairs_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/execute", methods=["POST"])
    async def api_tools_archive_cleanup_execute():
        blocked = _require_local("Archive cleanup execute")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(execute_archive_cleanup_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/llm-verify", methods=["POST"])
    async def api_tools_archive_cleanup_llm_verify():
        blocked = _require_local("Archive cleanup LLM verify")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(llm_verify_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/llm-verify-batch", methods=["POST"])
    async def api_tools_archive_cleanup_llm_verify_batch():
        blocked = _require_local("Archive cleanup LLM verify batch")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(llm_verify_batch_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/llm-config", methods=["GET"])
    async def api_tools_archive_cleanup_llm_config_get():
        blocked = _require_local("Archive cleanup LLM config")
        if blocked:
            return blocked
        payload, status = await run_db_sync(get_ac_llm_config_payload)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/llm-config", methods=["POST"])
    async def api_tools_archive_cleanup_llm_config_save():
        blocked = _require_local("Archive cleanup LLM config save")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(save_ac_llm_config_payload, data)
        return api_result(payload, status)

    @bp.route("/api/tools/archive-cleanup/list-models", methods=["POST"])
    async def api_tools_archive_cleanup_list_models():
        blocked = _require_local("Archive cleanup list models")
        if blocked:
            return blocked
        data, err = await require_json_dict(request)
        if err:
            return api_result(*err)
        payload, status = await run_db_sync(list_models_payload, data)
        return api_result(payload, status)
