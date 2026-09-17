"""Pull requests, notifications, discussions, releases, and repo stats routes."""

from __future__ import annotations

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from ._blueprint import bp

# ── Pull Requests ──────────────────────────────────────────────

@bp.route("/api/github/pulls/<label>", methods=["GET"])
async def fetch_pulls(label: str):
    """Fetch pull requests for an account's repositories."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_pulls as _fetch
    from .github_client import normalize_pull

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)
    if not acc.get("enabled"):
        return api_error(f"Account '{label}' is disabled", 400)

    state = request.args.get("state", "open")
    target_repo = request.args.get("repo", "")
    repos = [target_repo] if target_repo else acc.get("repos", [])

    all_pulls: list[dict] = []
    errors: list[str] = []
    for repo in repos:
        code, data = await run_db_sync(_fetch, acc["token"], repo, state)
        if code == 200 and isinstance(data, list):
            for raw in data:
                pr = normalize_pull(raw)
                pr["repo"] = repo
                all_pulls.append(pr)
        else:
            msg = data.get("message", f"HTTP {code}") if isinstance(data, dict) else str(code)
            errors.append(f"{repo}: {msg}")

    return api_result({"data": {"pulls": all_pulls, "count": len(all_pulls), "errors": errors}})


@bp.route("/api/github/pull/<label>/<path:repo>/<int:number>", methods=["GET"])
async def get_pull_detail(label: str, repo: str, number: int):
    """Get detailed PR info including diff stats and changed files."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_pull_detail as _detail
    from .github_client import fetch_pull_files, normalize_pull
    from .github_client_core import _validate_repo

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)
    if err := _validate_repo(repo):
        return api_error(err, 400)

    code, raw = await run_db_sync(_detail, acc["token"], repo, number)
    if code != 200:
        msg = raw.get("message", f"HTTP {code}") if isinstance(raw, dict) else str(code)
        return api_error(f"Failed to fetch PR: {msg}", code or 500)

    pr = normalize_pull(raw)
    pr["repo"] = repo

    # Fetch changed files
    f_code, files_raw = await run_db_sync(fetch_pull_files, acc["token"], repo, number)
    files = []
    if f_code == 200 and isinstance(files_raw, list):
        for f in files_raw[:50]:
            files.append({
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": (f.get("patch") or "")[:2000],
            })

    return api_result({"data": {"pull": pr, "files": files}})


# ── Notifications ──────────────────────────────────────────────

@bp.route("/api/github/notifications/<label>", methods=["GET"])
async def get_notifications(label: str):
    """Fetch notifications for an account."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_notifications as _fetch
    from .github_client import normalize_notification

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    show_all = request.args.get("all", "false") == "true"
    code, data = await run_db_sync(_fetch, acc["token"], show_all)
    if code != 200:
        msg = data.get("message", f"HTTP {code}") if isinstance(data, dict) else str(code)
        return api_error(f"Notifications fetch failed: {msg}", code or 500)

    notifs = [normalize_notification(n) for n in data] if isinstance(data, list) else []
    return api_result({"data": {"notifications": notifs, "count": len(notifs)}})


@bp.route("/api/github/notifications/<label>/<thread_id>", methods=["PATCH"])
async def mark_notif_read(label: str, thread_id: str):
    """Mark a notification as read."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import mark_notification_read

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    await run_db_sync(mark_notification_read, acc["token"], thread_id)
    return api_result({"ok": True})


@bp.route("/api/github/notifications/<label>/mark-all-read", methods=["POST"])
async def mark_all_read(label: str):
    """Mark all notifications as read."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import mark_all_notifications_read

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    await run_db_sync(mark_all_notifications_read, acc["token"])
    return api_result({"ok": True})


# ── Discussions ────────────────────────────────────────────────

@bp.route("/api/github/discussions/<label>", methods=["GET"])
async def get_discussions(label: str):
    """Fetch discussions for an account's repositories."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_discussions

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    target_repo = request.args.get("repo", "")
    repos = [target_repo] if target_repo else acc.get("repos", [])

    all_discussions: list[dict] = []
    errors: list[str] = []
    for repo in repos:
        code, data = await run_db_sync(fetch_discussions, acc["token"], repo)
        if code == 200 and isinstance(data, list):
            for d in data:
                d["repo"] = repo
                all_discussions.append(d)
        else:
            msg = data.get("message", f"HTTP {code}") if isinstance(data, dict) else str(code)
            errors.append(f"{repo}: {msg}")

    return api_result({
        "data": {"discussions": all_discussions, "count": len(all_discussions), "errors": errors}
    })


# ── Releases ───────────────────────────────────────────────────

@bp.route("/api/github/releases/<label>", methods=["GET"])
async def get_releases(label: str):
    """Fetch latest releases for an account's repositories."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_releases as _fetch
    from .github_client import normalize_release

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    target_repo = request.args.get("repo", "")
    repos = [target_repo] if target_repo else acc.get("repos", [])

    all_releases: list[dict] = []
    errors: list[str] = []
    for repo in repos:
        code, data = await run_db_sync(_fetch, acc["token"], repo, 5)
        if code == 200 and isinstance(data, list):
            for raw in data:
                rel = normalize_release(raw)
                rel["repo"] = repo
                all_releases.append(rel)
        else:
            msg = data.get("message", f"HTTP {code}") if isinstance(data, dict) else str(code)
            errors.append(f"{repo}: {msg}")

    return api_result({
        "data": {"releases": all_releases, "count": len(all_releases), "errors": errors}
    })


# ── Repository Stats ──────────────────────────────────────────

@bp.route("/api/github/repo-stats/<label>/<path:repo>", methods=["GET"])
async def get_repo_stats(label: str, repo: str):
    """Get repository statistics."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_repo_info, normalize_repo
    from .github_client_core import _validate_repo

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)
    if err := _validate_repo(repo):
        return api_error(err, 400)

    code, raw = await run_db_sync(fetch_repo_info, acc["token"], repo)
    if code != 200:
        msg = raw.get("message", f"HTTP {code}") if isinstance(raw, dict) else str(code)
        return api_error(f"Failed to fetch repo: {msg}", code or 500)

    return api_result({"data": normalize_repo(raw)})


@bp.route("/api/github/repo-stats-all/<label>", methods=["GET"])
async def get_all_repo_stats(label: str):
    """Get stats for all repositories in an account."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_repo_info, normalize_repo

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    repos_stats: list[dict] = []
    for repo in acc.get("repos", []):
        code, raw = await run_db_sync(fetch_repo_info, acc["token"], repo)
        if code == 200:
            repos_stats.append(normalize_repo(raw))

    return api_result({"data": {"repos": repos_stats}})
