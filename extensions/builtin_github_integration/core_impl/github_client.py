"""GitHub API client — re-export shim for backward compatibility.

Split into:
  - github_client_core.py  (HTTP request, issues, rate limit, issue write ops)
  - github_client_extra.py (PRs, notifications, discussions, releases, repo info)
"""

# Core: HTTP request, issues, rate limit, issue write operations
from .github_client_core import (  # noqa: F401
    _request,
    add_issue_comment,
    close_issue,
    create_issue,
    fetch_issue_comments,
    fetch_issues,
    get_rate_limit,
    normalize_issue,
)

# Extra: PRs, notifications, discussions, releases, repo info
from .github_client_extra import (  # noqa: F401
    fetch_discussions,
    fetch_notifications,
    fetch_pull_detail,
    fetch_pull_files,
    fetch_pulls,
    fetch_releases,
    fetch_repo_info,
    mark_all_notifications_read,
    mark_notification_read,
    normalize_notification,
    normalize_pull,
    normalize_release,
    normalize_repo,
)
