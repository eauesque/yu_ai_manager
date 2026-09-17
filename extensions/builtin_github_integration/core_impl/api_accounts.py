"""Account management and rate-limit API routes."""

from __future__ import annotations

import logging

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync

from ._blueprint import bp

logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope

# ── Account Management ──────────────────────────────────────────

@bp.route("/api/github/accounts", methods=["GET"])
async def list_accounts():
    """List registered GitHub accounts (tokens masked)."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import list_accounts as _list
    return api_result({"data": await run_db_sync(_list)})


@bp.route("/api/github/accounts", methods=["POST"])
async def add_account():
    """Add a new GitHub account.

    Body: {"label": str, "token": str, "repos": [str]}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    label = str(data.get("label", "")).strip()
    token = str(data.get("token", "")).strip()
    repos = data.get("repos", [])

    if not label:
        return api_error("label is required", 400)
    if not token:
        return api_error("token is required", 400)
    if not isinstance(repos, list):
        return api_error("repos must be a list", 400)

    try:
        from .account_store import add_account as _add
        result = await run_db_sync(_add, label, token, repos)
        return api_result({"data": result})
    except ValueError:
        logger.exception("Failed to add GitHub account", extra={"label": label})
        return api_error("GitHub account could not be added", 409)


@bp.route("/api/github/accounts/<label>", methods=["PUT"])
async def update_account(label: str):
    """Update a GitHub account.

    Body: {"token": str?, "repos": [str]?, "enabled": bool?}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    from .account_store import update_account as _update
    result = await run_db_sync(
        _update, label,
        token=data.get("token"),
        repos=data.get("repos"),
        enabled=data.get("enabled"),
    )
    if result is None:
        return api_error(f"Account '{label}' not found", 404)
    return api_result({"data": result})


@bp.route("/api/github/accounts/<label>", methods=["DELETE"])
async def remove_account(label: str):
    """Remove a GitHub account."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import remove_account as _remove
    ok = await run_db_sync(_remove, label)
    if not ok:
        return api_error(f"Account '{label}' not found", 404)
    return api_result({"ok": True})


# ── Rate Limit ──────────────────────────────────────────────────

@bp.route("/api/github/rate-limit/<label>", methods=["GET"])
async def rate_limit(label: str):
    """Check GitHub API rate limit for an account."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import get_rate_limit

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    result = await run_db_sync(get_rate_limit, acc["token"])
    return api_result({"data": result})
