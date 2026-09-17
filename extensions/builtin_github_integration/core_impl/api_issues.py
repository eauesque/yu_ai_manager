"""Issue fetching, triage, issue detail, creation, and triage prompt routes."""

from __future__ import annotations

from quart import request

from core.infra_core.api_errors import api_error, api_result
from core.services_core.db_async import run_db_sync
from core.web.auth_helpers import require_admin_scope as _require_admin_scope

from ._blueprint import bp

# ── Issue Fetching ──────────────────────────────────────────────

@bp.route("/api/github/issues/<label>", methods=["GET"])
async def fetch_issues(label: str):
    """Fetch issues for a specific account's repositories.

    Query params: state (open/closed/all), labels, since, repo (specific repo)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_issues as _fetch
    from .github_client import normalize_issue

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)
    if not acc.get("enabled"):
        return api_error(f"Account '{label}' is disabled", 400)

    state = request.args.get("state", "open")
    labels_filter = request.args.get("labels", "")
    since = request.args.get("since", "")
    target_repo = request.args.get("repo", "")

    repos = [target_repo] if target_repo else acc.get("repos", [])
    if not repos:
        return api_error("No repositories configured for this account", 400)

    all_issues: list[dict] = []
    errors: list[str] = []

    for repo in repos:
        code, data = await run_db_sync(
            _fetch, acc["token"], repo, state, labels_filter, since
        )
        if code == 200 and isinstance(data, list):
            for raw in data:
                issue = normalize_issue(raw)
                issue["repo"] = repo
                if not issue.get("is_pull_request"):
                    all_issues.append(issue)
        else:
            msg = data.get("message", f"HTTP {code}") if isinstance(data, dict) else str(code)
            errors.append(f"{repo}: {msg}")

    return api_result({
        "data": {
            "issues": all_issues,
            "count": len(all_issues),
            "errors": errors,
        }
    })


# ── Triage ──────────────────────────────────────────────────────

@bp.route("/api/github/triage/<label>", methods=["POST"])
async def triage_issues(label: str):
    """Fetch and triage issues for an account.

    Body: {"state": "open", "since": ""}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account, get_triage_config
    from .github_client import fetch_issues as _fetch
    from .github_client import normalize_issue
    from .triage import triage_batch

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    data = await request.get_json(silent=True) or {}
    state = str(data.get("state", "open"))
    since = str(data.get("since", ""))

    triage_cfg = await run_db_sync(get_triage_config)
    repos = acc.get("repos", [])

    all_issues: list[dict] = []
    for repo in repos:
        code, raw_list = await run_db_sync(
            _fetch, acc["token"], repo, state, "", since
        )
        if code == 200 and isinstance(raw_list, list):
            for raw in raw_list:
                issue = normalize_issue(raw)
                issue["repo"] = repo
                if not issue.get("is_pull_request"):
                    all_issues.append(issue)

    report = triage_batch(
        all_issues,
        skip_labels=triage_cfg.get("auto_skip_labels"),
        language_filter=triage_cfg.get("language_filter", "en"),
    )

    return api_result({"data": report})


# ── Issue Detail (for Claude Code) ──────────────────────────────

@bp.route("/api/github/issue/<label>/<path:repo>/<int:number>", methods=["GET"])
async def get_issue_detail(label: str, repo: str, number: int):
    """Get detailed issue info formatted for Claude Code consumption."""
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import fetch_issue_comments, normalize_issue
    from .github_client import fetch_issues as _fetch
    from .github_client_core import _validate_repo
    from .triage import format_for_claude_code

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)
    if err := _validate_repo(repo):
        return api_error(err, 400)

    # Fetch the specific issue
    code, data = await run_db_sync(
        _fetch, acc["token"], repo, "all", "", "", 1, 1
    )

    # Fetch issue directly
    from .github_client import _request
    code, raw = await run_db_sync(
        _request, f"/repos/{repo}/issues/{number}", acc["token"]
    )
    if code != 200:
        msg = raw.get("message", f"HTTP {code}") if isinstance(raw, dict) else str(code)
        return api_error(f"Failed to fetch issue: {msg}", code or 500)

    issue = normalize_issue(raw)
    issue["repo"] = repo

    # Fetch comments
    comments = []
    if issue.get("comments_count", 0) > 0:
        c_code, c_data = await run_db_sync(
            fetch_issue_comments, acc["token"], repo, number
        )
        if c_code == 200 and isinstance(c_data, list):
            comments = c_data

    formatted = format_for_claude_code(issue, comments)

    return api_result({
        "data": {
            "issue": issue,
            "formatted": formatted,
            "comments_count": len(comments),
        }
    })


# ── Issue Creation ─────────────────────────────────────────────

@bp.route("/api/github/issues/<label>", methods=["POST"])
async def create_issue_endpoint(label: str):
    """Create a new issue.

    Body: {"repo": str, "title": str, "body": str?, "labels": [str]?}
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import get_account
    from .github_client import create_issue, normalize_issue

    acc = await run_db_sync(get_account, label)
    if not acc:
        return api_error(f"Account '{label}' not found", 404)

    data = await request.get_json(silent=True) or {}
    repo = str(data.get("repo", "")).strip()
    title = str(data.get("title", "")).strip()
    body_text = str(data.get("body", ""))
    labels = data.get("labels", [])

    if not repo:
        return api_error("repo is required", 400)
    if not title:
        return api_error("title is required", 400)
    if repo not in acc.get("repos", []):
        return api_error(f"Repo '{repo}' not in account's configured repos", 400)

    code, raw = await run_db_sync(
        create_issue, acc["token"], repo, title, body_text, labels or None
    )
    if code not in (200, 201):
        msg = raw.get("message", f"HTTP {code}") if isinstance(raw, dict) else str(code)
        return api_error(f"Failed to create issue: {msg}", code or 500)

    return api_result({"data": normalize_issue(raw)})


# ── Triage Prompts ─────────────────────────────────────────────

@bp.route("/api/github/triage-prompts", methods=["GET"])
async def get_triage_prompts_endpoint():
    """Get triage prompts with optional per-repo resolution.

    Query params: repo (optional, "owner/repo" format)
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    from .account_store import (
        TRIAGE_PROMPT_DEFAULTS,
        get_triage_prompts,
        get_triage_prompts_per_repo,
    )
    repo = request.args.get("repo", "")
    prompts = await run_db_sync(get_triage_prompts, repo)
    global_prompts = await run_db_sync(get_triage_prompts)
    per_repo = await run_db_sync(get_triage_prompts_per_repo)
    return api_result({"data": {
        "prompts": prompts,
        "global": global_prompts,
        "per_repo": per_repo,
        "defaults": TRIAGE_PROMPT_DEFAULTS,
        "repo": repo,
    }})


@bp.route("/api/github/triage-prompts", methods=["PUT"])
async def save_triage_prompts_endpoint():
    """Update triage prompts (global or per-repo).

    Body: {"issue": str?, "pr": str?, "discussion": str?, "repo": str?}
    If repo is given, saves as per-repo override. Empty string clears override.
    """
    auth_err = _require_admin_scope()
    if auth_err:
        return auth_err
    data = await request.get_json(silent=True) or {}
    from .account_store import save_triage_prompts
    repo = str(data.get("repo", "")).strip()
    result = await run_db_sync(
        save_triage_prompts,
        issue=data.get("issue"),
        pr=data.get("pr"),
        discussion=data.get("discussion"),
        repo=repo,
    )
    return api_result({"data": result})
