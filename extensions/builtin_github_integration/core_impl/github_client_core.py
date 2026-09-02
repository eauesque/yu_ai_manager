"""GitHub API client — core HTTP request + issue/comment operations."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode as _urlencode

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")
_USER_AGENT = "YU-AI-Manager-GitHub-Integration/1.0"

# Rate limit tracking
_rate_remaining = 5000
_rate_reset = 0.0


def _validate_repo(repo: str) -> str | None:
    """Return error string if repo is not in owner/repo format, else None."""
    if not _REPO_RE.match(repo):
        return f"Invalid repo format: '{repo}'. Expected 'owner/repo'."
    return None


def _request(
    path: str,
    token: str,
    params: dict[str, str] | None = None,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> tuple[int, Any]:
    """Make an authenticated GitHub API request.

    Returns (status_code, parsed_json).
    """
    global _rate_remaining, _rate_reset

    # Check rate limit
    if _rate_remaining <= 5 and time.time() < _rate_reset:
        wait = int(_rate_reset - time.time()) + 1
        logger.warning("GitHub API rate limit near zero, waiting %ds", wait)
        return 429, {"message": f"Rate limit reached, resets in {wait}s"}

    url = _API_BASE + path
    if params:
        url += "?" + _urlencode(params)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        # Update rate limit info
        _rate_remaining = int(resp.headers.get("X-RateLimit-Remaining", 5000))
        reset_ts = resp.headers.get("X-RateLimit-Reset", "0")
        _rate_reset = float(reset_ts)

        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            data = {"message": body[:500]}
        return e.code, data
    except Exception as e:
        logger.warning("GitHub API request failed: %s", e)
        return 0, {"message": "Request failed"}


def fetch_issues(
    token: str,
    repo: str,
    state: str = "open",
    labels: str = "",
    since: str = "",
    per_page: int = 30,
    page: int = 1,
) -> tuple[int, list[dict] | dict]:
    """Fetch issues for a repository.

    Args:
        token: GitHub PAT
        repo: "owner/repo" format
        state: "open", "closed", or "all"
        labels: Comma-separated label names
        since: ISO 8601 timestamp (only issues updated after this)
        per_page: Results per page (max 100)
        page: Page number

    Returns:
        (status_code, list_of_issues or error_dict)
    """
    params: dict[str, str] = {
        "state": state,
        "per_page": str(min(per_page, 100)),
        "page": str(page),
        "sort": "created",
        "direction": "desc",
    }
    if labels:
        params["labels"] = labels
    if since:
        params["since"] = since

    return _request(f"/repos/{repo}/issues", token, params)


def fetch_issue_comments(
    token: str, repo: str, issue_number: int, per_page: int = 10
) -> tuple[int, list[dict] | dict]:
    """Fetch comments for a specific issue."""
    params = {"per_page": str(min(per_page, 100))}
    return _request(
        f"/repos/{repo}/issues/{issue_number}/comments", token, params
    )


def get_rate_limit(token: str) -> dict:
    """Get current rate limit status."""
    code, data = _request("/rate_limit", token)
    if code == 200:
        core = data.get("resources", {}).get("core", {})
        return {
            "remaining": core.get("remaining", 0),
            "limit": core.get("limit", 0),
            "reset": core.get("reset", 0),
            "reset_at": datetime.fromtimestamp(
                core.get("reset", 0), tz=UTC
            ).isoformat() if core.get("reset") else "",
        }
    return {"error": data.get("message", "Failed to fetch rate limit")}


def normalize_issue(raw: dict) -> dict:
    """Normalize a GitHub API issue into a simplified structure."""
    return {
        "number": raw.get("number"),
        "title": raw.get("title", ""),
        "state": raw.get("state", ""),
        "user": raw.get("user", {}).get("login", ""),
        "labels": [l.get("name", "") for l in raw.get("labels", [])],
        "created_at": raw.get("created_at", ""),
        "updated_at": raw.get("updated_at", ""),
        "body": (raw.get("body") or "")[:3000],
        "comments_count": raw.get("comments", 0),
        "html_url": raw.get("html_url", ""),
        "is_pull_request": "pull_request" in raw,
    }


# -- Issue write operations --

def create_issue(
    token: str, repo: str, title: str, body: str = "",
    labels: list[str] | None = None,
) -> tuple[int, dict]:
    """Create a new issue in a repository."""
    payload: dict[str, Any] = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    return _request(
        f"/repos/{repo}/issues", token,
        method="POST", body=payload,
    )


def close_issue(
    token: str, repo: str, issue_number: int
) -> tuple[int, dict]:
    """Close an issue by setting its state to 'closed'."""
    return _request(
        f"/repos/{repo}/issues/{issue_number}", token,
        method="PATCH", body={"state": "closed"},
    )


def add_issue_comment(
    token: str, repo: str, issue_number: int, body: str
) -> tuple[int, dict]:
    """Post a comment on an issue."""
    return _request(
        f"/repos/{repo}/issues/{issue_number}/comments", token,
        method="POST", body={"body": body},
    )
