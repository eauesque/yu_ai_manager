"""Monthly report API routes."""

import re

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_api import get_readonly_db
from core.services_core.db_async import run_db_sync
from core.stats_api.stats_cache import get_cached_monthly_report

bp = Blueprint("monthly_report", __name__)

_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/stats/monthly-report")
async def api_monthly_report():
    """Return monthly report data."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    month = request.args.get("month", "")
    if not month:
        # Default: current month
        import datetime
        # Local calendar month, same value `date.today()` gave. Not
        # `now(UTC)`: under a positive offset that can be last month.
        month = (
            datetime.datetime.now(tz=datetime.UTC)
            .astimezone()
            .strftime("%Y-%m")
        )

    if not _MONTH_RE.match(month):
        return api_error("Invalid month format (expected YYYY-MM)", 400)

    include_trophies = request.args.get("include_trophies", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }

    def _fetch(m, include_trophies_flag):
        con = get_readonly_db()
        if include_trophies_flag:
            return get_cached_monthly_report(con, m)
        from core.stats_api.monthly_report import build_monthly_report

        return build_monthly_report(con, m, include_trophies=False)

    data = await run_db_sync(_fetch, month, include_trophies)
    return api_success(data=data)
