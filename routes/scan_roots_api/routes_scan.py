"""Route registrations for scan-all APIs."""

from quart import request

from core.infra_core.api_errors import api_result
from core.infra_core.api_request import require_json_dict
from core.scan_roots_api.scan_all import run_scan_all_roots
from core.services_core.db_async import run_db_sync


def register_scan_roots_scan_routes(bp) -> None:
    @bp.route("/api/scan-all", methods=["POST"])
    async def api_scan_all_roots():
        """Scan all scan roots (background)."""
        data, err = await require_json_dict(request)
        if err:
            return api_result(err[0], err[1])
        return await run_db_sync(run_scan_all_roots, data)
