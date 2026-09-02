import logging

from quart import request

from core.analysis_api.server_api_models import (
    AnalysisServerCreateRequest,
    AnalysisServerReorderRequest,
    AnalysisServerUpdateRequest,
)
from core.analysis_api.server_crud import (
    add_server,
    get_servers_with_status,
    migrate_from_legacy,
    remove_server,
    reorder_servers,
    set_active_server,
    test_server,
    update_server,
)
from core.analysis_api.server_discovery_candidates import get_discovered_candidates
from core.analysis_api.server_discovery_match import (
    ignore_discovered_candidate,
    match_discovered_candidate,
    unignore_discovered_candidate,
    unmatch_discovered_candidate,
)
from core.analysis_api.server_discovery_registry import (
    register_discovered_candidate,
    run_discovered_candidate_test,
)
from core.analysis_api.server_discovery_request_models import (
    IgnoreDiscoveredCandidateRequest,
    MatchDiscoveredCandidateRequest,
    RegisterDiscoveredCandidateRequest,
    TestDiscoveredCandidateRequest,
)
from core.analysis_api.trend_history_ops import delete_trend_history, get_trend_history
from core.infra_core.api_errors import api_error, api_result
from core.infra_core.api_request import require_json_model
from core.services_core.db_async import run_db_sync

logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def register_analysis_server_routes(bp):
    @bp.route("/api/analysis/servers/discovered")
    async def api_servers_discovered():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return api_result(
            {"candidates": await run_db_sync(get_discovered_candidates)},
            200,
        )

    @bp.route("/api/analysis/servers/discovered/register", methods=["POST"])
    async def api_servers_discovered_register():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, RegisterDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(register_discovered_candidate, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 201)

    @bp.route("/api/analysis/servers/discovered/test", methods=["POST"])
    async def api_servers_discovered_test():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, TestDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(run_discovered_candidate_test, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/discovered/match", methods=["POST"])
    async def api_servers_discovered_match():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, MatchDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(match_discovered_candidate, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/discovered/match", methods=["DELETE"])
    async def api_servers_discovered_unmatch():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, IgnoreDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(unmatch_discovered_candidate, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/discovered/ignore", methods=["POST"])
    async def api_servers_discovered_ignore():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, IgnoreDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(ignore_discovered_candidate, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/discovered/ignore", methods=["DELETE"])
    async def api_servers_discovered_unignore():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, IgnoreDiscoveredCandidateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(unignore_discovered_candidate, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers")
    async def api_servers_list():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        return api_result({"servers": await run_db_sync(get_servers_with_status)}, 200)

    @bp.route("/api/analysis/servers", methods=["POST"])
    async def api_servers_add():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, AnalysisServerCreateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(add_server, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 201)

    @bp.route("/api/analysis/servers/<server_id>", methods=["PUT"])
    async def api_servers_update(server_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, AnalysisServerUpdateRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(update_server, server_id, data.model_dump(exclude_none=True))
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/<server_id>", methods=["DELETE"])
    async def api_servers_delete(server_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = await run_db_sync(remove_server, server_id)
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/<server_id>/activate", methods=["POST"])
    async def api_servers_activate(server_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = await run_db_sync(set_active_server, server_id)
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/<server_id>/test", methods=["POST"])
    async def api_servers_test(server_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = await run_db_sync(test_server, server_id)
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/reorder", methods=["PUT"])
    async def api_servers_reorder():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        data, err = await require_json_model(request, AnalysisServerReorderRequest)
        if err:
            return api_result(err[0], err[1])
        assert data is not None
        result = await run_db_sync(reorder_servers, data.server_ids)
        return api_result(result, 200)

    @bp.route("/api/analysis/servers/migrate", methods=["POST"])
    async def api_servers_migrate():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        result = await run_db_sync(migrate_from_legacy)
        if not result.get("success"):
            return api_error(result.get("error", "Failed"), 400)
        return api_result(result, 200)

    @bp.route("/api/analysis/trends/history")
    async def api_trend_history():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            limit = min(int(request.args.get("limit", 20)), 50)
            offset = max(int(request.args.get("offset", 0)), 0)
            items = await run_db_sync(get_trend_history, limit, offset)
            return api_result({"items": items}, 200)
        except Exception:
            logger.exception("trend_history error")
            return api_error("Failed to get trend history", 500)

    @bp.route("/api/analysis/trends/history/<int:history_id>", methods=["DELETE"])
    async def api_trend_history_delete(history_id):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        try:
            deleted = await run_db_sync(delete_trend_history, history_id)
            if not deleted:
                return api_error("Not found", 404)
            return api_result({"deleted": True}, 200)
        except Exception:
            logger.exception("trend_history delete error for id=%d", history_id)
            return api_error("Failed to delete trend history", 500)
