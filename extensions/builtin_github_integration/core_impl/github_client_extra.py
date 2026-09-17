"""GitHub API client — PRs, notifications, discussions, releases, repo info."""

from __future__ import annotations

from typing import Any

from .github_client_core import _request

# -- Pull Requests --

def fetch_pulls(
    token: str,
    repo: str,
    state: str = "open",
    per_page: int = 30,
    page: int = 1,
) -> tuple[int, list[dict] | dict]:
    """Fetch pull requests for a repository."""
    params: dict[str, str] = {
        "state": state,
        "per_page": str(min(per_page, 100)),
        "page": str(page),
        "sort": "created",
        "direction": "desc",
    }
    return _request(f"/repos/{repo}/pulls", token, params)


def fetch_pull_detail(
    token: str, repo: str, number: int
) -> tuple[int, dict]:
    """Fetch detailed pull request info (includes merge status, diff stats)."""
    return _request(f"/repos/{repo}/pulls/{number}", token)


def fetch_pull_files(
    token: str, repo: str, number: int, per_page: int = 100
) -> tuple[int, list[dict] | dict]:
    """Fetch files changed in a pull request."""
    return _request(
        f"/repos/{repo}/pulls/{number}/files", token,
        {"per_page": str(min(per_page, 100))},
    )


def normalize_pull(raw: dict) -> dict:
    """Normalize a GitHub PR into a simplified structure."""
    return {
        "number": raw.get("number"),
        "title": raw.get("title", ""),
        "state": raw.get("state", ""),
        "user": raw.get("user", {}).get("login", ""),
        "labels": [la.get("name", "") for la in raw.get("labels", [])],
        "created_at": raw.get("created_at", ""),
        "updated_at": raw.get("updated_at", ""),
        "body": (raw.get("body") or "")[:3000],
        "html_url": raw.get("html_url", ""),
        "head_ref": raw.get("head", {}).get("ref", ""),
        "base_ref": raw.get("base", {}).get("ref", ""),
        "draft": raw.get("draft", False),
        "merged": raw.get("merged", False) if "merged" in raw else None,
        "mergeable": raw.get("mergeable"),
        "additions": raw.get("additions", 0),
        "deletions": raw.get("deletions", 0),
        "changed_files": raw.get("changed_files", 0),
        "comments_count": raw.get("comments", 0),
        "review_comments": raw.get("review_comments", 0),
        "repo": raw.get("base", {}).get("repo", {}).get("full_name", ""),
    }


# -- Notifications --

def fetch_notifications(
    token: str, all_notifs: bool = False, per_page: int = 50
) -> tuple[int, list[dict] | dict]:
    """Fetch notifications for the authenticated user."""
    params = {
        "per_page": str(min(per_page, 100)),
        "all": "true" if all_notifs else "false",
    }
    return _request("/notifications", token, params)


def mark_notification_read(token: str, thread_id: str) -> tuple[int, Any]:
    """Mark a single notification thread as read."""
    return _request(
        f"/notifications/threads/{thread_id}", token,
        method="PATCH",
    )


def mark_all_notifications_read(token: str) -> tuple[int, Any]:
    """Mark all notifications as read."""
    return _request("/notifications", token, method="PUT")


def normalize_notification(raw: dict) -> dict:
    """Normalize a GitHub notification."""
    subject = raw.get("subject", {})
    repo = raw.get("repository", {})
    # Extract issue/PR number from URL if available
    sub_url = subject.get("url") or ""
    number = ""
    if "/issues/" in sub_url or "/pulls/" in sub_url:
        number = sub_url.rsplit("/", 1)[-1]
    return {
        "id": raw.get("id", ""),
        "reason": raw.get("reason", ""),
        "unread": raw.get("unread", False),
        "updated_at": raw.get("updated_at", ""),
        "subject_title": subject.get("title", ""),
        "subject_type": subject.get("type", ""),
        "subject_number": number,
        "repo_full_name": repo.get("full_name", ""),
        "repo_html_url": repo.get("html_url", ""),
    }


# -- Discussions (GraphQL) --

_DISCUSSIONS_QUERY = """
query($owner: String!, $name: String!, $first: Int!) {
  repository(owner: $owner, name: $name) {
    discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        number
        title
        author { login }
        createdAt
        updatedAt
        bodyText
        url
        category { name emoji }
        comments { totalCount }
        labels(first: 5) { nodes { name } }
        answerChosenAt
      }
    }
  }
}
"""


def fetch_discussions(
    token: str, repo: str, first: int = 20
) -> tuple[int, list[dict] | dict]:
    """Fetch discussions via GraphQL API."""
    parts = repo.split("/", 1)
    if len(parts) != 2:
        return 400, {"message": f"Invalid repo format: {repo}"}
    owner, name = parts

    code, data = _request(
        "/graphql", token,
        method="POST",
        body={
            "query": _DISCUSSIONS_QUERY,
            "variables": {"owner": owner, "name": name, "first": first},
        },
    )
    if code != 200:
        return code, data

    errors = data.get("errors")
    if errors:
        return 422, {"message": errors[0].get("message", "GraphQL error")}

    nodes = (
        data.get("data", {})
        .get("repository", {})
        .get("discussions", {})
        .get("nodes", [])
    )
    return 200, [_normalize_discussion(n) for n in nodes]


def _normalize_discussion(raw: dict) -> dict:
    """Normalize a GraphQL discussion node."""
    cat = raw.get("category") or {}
    return {
        "number": raw.get("number"),
        "title": raw.get("title", ""),
        "author": (raw.get("author") or {}).get("login", ""),
        "created_at": raw.get("createdAt", ""),
        "updated_at": raw.get("updatedAt", ""),
        "body": (raw.get("bodyText") or "")[:1500],
        "url": raw.get("url", ""),
        "category": cat.get("name", ""),
        "category_emoji": cat.get("emoji", ""),
        "comments_count": raw.get("comments", {}).get("totalCount", 0),
        "labels": [la.get("name", "") for la in
                   (raw.get("labels") or {}).get("nodes", [])],
        "answered": raw.get("answerChosenAt") is not None,
    }


# -- Releases --

def fetch_releases(
    token: str, repo: str, per_page: int = 10
) -> tuple[int, list[dict] | dict]:
    """Fetch releases for a repository."""
    return _request(
        f"/repos/{repo}/releases", token,
        {"per_page": str(min(per_page, 30))},
    )


def normalize_release(raw: dict) -> dict:
    """Normalize a GitHub release."""
    return {
        "tag_name": raw.get("tag_name", ""),
        "name": raw.get("name", ""),
        "draft": raw.get("draft", False),
        "prerelease": raw.get("prerelease", False),
        "published_at": raw.get("published_at", ""),
        "html_url": raw.get("html_url", ""),
        "body": (raw.get("body") or "")[:2000],
        "author": raw.get("author", {}).get("login", ""),
    }


# -- Repository Info --

def fetch_repo_info(token: str, repo: str) -> tuple[int, dict]:
    """Fetch repository info (stars, forks, etc.)."""
    return _request(f"/repos/{repo}", token)


def normalize_repo(raw: dict) -> dict:
    """Normalize repo info to essential stats."""
    return {
        "full_name": raw.get("full_name", ""),
        "description": (raw.get("description") or "")[:300],
        "stars": raw.get("stargazers_count", 0),
        "forks": raw.get("forks_count", 0),
        "open_issues": raw.get("open_issues_count", 0),
        "watchers": raw.get("watchers_count", 0),
        "language": raw.get("language", ""),
        "html_url": raw.get("html_url", ""),
        "updated_at": raw.get("updated_at", ""),
        "default_branch": raw.get("default_branch", "main"),
        "topics": raw.get("topics", []),
    }
