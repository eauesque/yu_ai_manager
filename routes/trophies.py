"""Trophy API routes."""

from importlib import import_module

from quart import Blueprint

from core.infra_core.api_errors import api_success
from core.services_core.db_api import get_readonly_db
from core.services_core.db_async import run_db_sync

# Import from relocated trophy extension
_trophy_store = import_module("extensions.builtin_trophy.core_impl.trophy_store")
list_trophies = _trophy_store.list_trophies

bp = Blueprint("trophies", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/trophies")
async def api_list_trophies():
    """List all trophies (earned + unearned silhouettes)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err

    def _fetch():
        con = get_readonly_db()
        return list_trophies(con)

    data = await run_db_sync(_fetch)
    return api_success(data=data)
