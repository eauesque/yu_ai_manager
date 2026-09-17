"""Source code browsing API -- read-only.

Safely exposes project source code for MCP / external agents.
All endpoints are GET only (read-only).
"""

from quart import Blueprint, request

from core.infra_core.api_errors import api_result
from core.services_core.db_async import run_db_sync
from core.source_core.source_browser_ops import source_read, source_search, source_tree

bp = Blueprint("source_api", __name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


@bp.route("/api/source/tree")
async def api_source_tree():
    """Get directory tree.

    Query params:
        path: Relative path (default: project root)
        depth: Traversal depth 1-6 (default: 3)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    rel_path = request.args.get("path", "")
    depth = request.args.get("depth", "3")
    try:
        depth_int = int(depth)
    except ValueError:
        depth_int = 3

    result = await run_db_sync(source_tree, rel_path, depth_int)
    status = 200 if result.get("ok") else 400
    return api_result(result, status)


@bp.route("/api/source/read")
async def api_source_read():
    """Read file contents with line numbers.

    Query params:
        path: Relative file path (required)
        offset: Starting line (default: 0)
        limit: Maximum number of lines (default: 2000)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    rel_path = request.args.get("path", "")
    offset = request.args.get("offset", "0")
    limit = request.args.get("limit", "2000")
    try:
        offset_int = int(offset)
    except ValueError:
        offset_int = 0
    try:
        limit_int = int(limit)
    except ValueError:
        limit_int = 2000

    result = await run_db_sync(source_read, rel_path, offset_int, limit_int)
    status = 200 if result.get("ok") else 400
    return api_result(result, status)


@bp.route("/api/source/search")
async def api_source_search():
    """Search text within source code.

    Query params:
        q: Search query (required, 2+ characters)
        glob: Filename filter (e.g., "*.py")
        limit: Maximum number of results (default: 30, max: 50)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    query = request.args.get("q", "")
    glob_pattern = request.args.get("glob", "")
    limit = request.args.get("limit", "30")
    try:
        limit_int = int(limit)
    except ValueError:
        limit_int = 30

    result = await run_db_sync(source_search, query, glob_pattern, limit_int)
    status = 200 if result.get("ok") else 400
    return api_result(result, status)
