"""Issue and triage prompt tools for GitHub MCP integration."""

from mcp.server.fastmcp import FastMCP

from .github_tools_common import as_json


def register_github_triage_tools(mcp: FastMCP, client):
    """Register GitHub issue and triage prompt tools."""

    # ── Account Management ──────────────────────────────────────────

    @mcp.tool()
    def github_list_accounts() -> str:
        """List registered GitHub accounts (tokens masked)."""
        return as_json(client._request("GET", "/api/github/accounts"))

    @mcp.tool()
    def github_add_account(label: str, token: str, repos: list | None = None) -> str:
        """Add a new GitHub account.

        Args:
            label: Unique account identifier.
            token: GitHub personal access token.
            repos: List of repositories in "owner/repo" format (default empty).
        """
        body = {"label": label, "token": token, "repos": repos or []}
        return as_json(client._request("POST", "/api/github/accounts", body=body))

    @mcp.tool()
    def github_update_account(
        label: str,
        token: str = "",
        repos: list | None = None,
        enabled: bool | None = None,
    ) -> str:
        """Update an existing GitHub account.

        Args:
            label: Account identifier to update.
            token: New token (omit to keep existing).
            repos: New repository list (omit to keep existing).
            enabled: Enable or disable the account (omit to keep existing).
        """
        body = {}
        if token:
            body["token"] = token
        if repos is not None:
            body["repos"] = repos
        if enabled is not None:
            body["enabled"] = enabled
        return as_json(client._request("PUT", f"/api/github/accounts/{label}", body=body))

    @mcp.tool()
    def github_remove_account(label: str) -> str:
        """Remove a registered GitHub account.

        Args:
            label: Account identifier to remove.
        """
        return as_json(client._request("DELETE", f"/api/github/accounts/{label}"))

    # ── Issue Fetching ──────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_issues(
        account_label: str,
        state: str = "open",
        since: str = "",
        repo: str = "",
        labels: str = "",
    ) -> str:
        """Fetch GitHub issues for an account's repositories.

        Args:
            account_label: Account identifier.
            state: Issue state filter: open, closed, or all (default "open").
            since: ISO 8601 timestamp to filter issues updated after this date.
            repo: Specific repository in "owner/repo" format (fetches all if omitted).
            labels: Comma-separated label names to filter by.
        """
        params = {"state": state}
        if since:
            params["since"] = since
        if repo:
            params["repo"] = repo
        if labels:
            params["labels"] = labels
        return as_json(client._request("GET", f"/api/github/issues/{account_label}", params=params))

    @mcp.tool()
    def github_triage_issues(
        account_label: str,
        state: str = "open",
        since: str = "",
    ) -> str:
        """Fetch and triage GitHub issues."""
        body = {"state": state}
        if since:
            body["since"] = since
        return as_json(client._request("POST", f"/api/github/triage/{account_label}", body=body))

    @mcp.tool()
    def github_create_issue(
        account_label: str,
        repo: str,
        title: str,
        body: str = "",
        labels: list | None = None,
    ) -> str:
        """Create a new GitHub issue.

        Args:
            account_label: Account identifier.
            repo: Repository in "owner/repo" format (must be in account's repo list).
            title: Issue title.
            body: Issue body text (optional).
            labels: List of label names to apply (optional).
        """
        payload = {"repo": repo, "title": title, "body": body, "labels": labels or []}
        return as_json(client._request("POST", f"/api/github/issues/{account_label}", body=payload))

    # ── Issue Detail ────────────────────────────────────────────────

    @mcp.tool()
    def github_get_issue_detail(account_label: str, repo: str, issue_number: int) -> str:
        """Get detailed issue info formatted for analysis."""
        return as_json(client._request("GET", f"/api/github/issue/{account_label}/{repo}/{issue_number}"))

    # ── Pull Requests ───────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_pulls(account_label: str, repo: str = "", state: str = "open") -> str:
        """Fetch pull requests for an account's repositories.

        Args:
            account_label: Account identifier.
            repo: Specific repository in "owner/repo" format (fetches all if omitted).
            state: PR state filter: open, closed, or all (default "open").
        """
        params = {"state": state}
        if repo:
            params["repo"] = repo
        return as_json(client._request("GET", f"/api/github/pulls/{account_label}", params=params))

    @mcp.tool()
    def github_get_pr_detail(account_label: str, repo: str, number: int) -> str:
        """Get detailed PR info including diff stats and changed files.

        Args:
            account_label: Account identifier.
            repo: Repository in "owner/repo" format.
            number: Pull request number.
        """
        return as_json(client._request("GET", f"/api/github/pull/{account_label}/{repo}/{number}"))

    # ── Notifications ───────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_notifications(account_label: str, show_all: bool = False) -> str:
        """Fetch notifications for a GitHub account.

        Args:
            account_label: Account identifier.
            show_all: Include read notifications when True (default False).
        """
        params = {"all": "true" if show_all else "false"}
        return as_json(client._request("GET", f"/api/github/notifications/{account_label}", params=params))

    @mcp.tool()
    def github_mark_notification_read(account_label: str, thread_id: str) -> str:
        """Mark a specific notification thread as read.

        Args:
            account_label: Account identifier.
            thread_id: Notification thread ID.
        """
        return as_json(client._request("PATCH", f"/api/github/notifications/{account_label}/{thread_id}"))

    @mcp.tool()
    def github_mark_all_notifications_read(account_label: str) -> str:
        """Mark all notifications as read for a GitHub account.

        Args:
            account_label: Account identifier.
        """
        return as_json(client._request("POST", f"/api/github/notifications/{account_label}/mark-all-read", body={}))

    # ── Discussions ─────────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_discussions(account_label: str, repo: str = "") -> str:
        """Fetch discussions for an account's repositories.

        Args:
            account_label: Account identifier.
            repo: Specific repository in "owner/repo" format (fetches all if omitted).
        """
        params = {}
        if repo:
            params["repo"] = repo
        return as_json(client._request("GET", f"/api/github/discussions/{account_label}", params=params))

    # ── Releases ────────────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_releases(account_label: str, repo: str = "") -> str:
        """Fetch latest releases for an account's repositories.

        Args:
            account_label: Account identifier.
            repo: Specific repository in "owner/repo" format (fetches all if omitted).
        """
        params = {}
        if repo:
            params["repo"] = repo
        return as_json(client._request("GET", f"/api/github/releases/{account_label}", params=params))

    # ── Repository Stats ─────────────────────────────────────────────

    @mcp.tool()
    def github_fetch_repo_stats(account_label: str, repo: str) -> str:
        """Get statistics for a specific repository.

        Args:
            account_label: Account identifier.
            repo: Repository in "owner/repo" format.
        """
        return as_json(client._request("GET", f"/api/github/repo-stats/{account_label}/{repo}"))

    @mcp.tool()
    def github_fetch_all_repo_stats(account_label: str) -> str:
        """Get statistics for all repositories configured in an account.

        Args:
            account_label: Account identifier.
        """
        return as_json(client._request("GET", f"/api/github/repo-stats-all/{account_label}"))

    # ── Rate Limit ──────────────────────────────────────────────────

    @mcp.tool()
    def github_rate_limit(account_label: str) -> str:
        """Check GitHub API rate limit for an account."""
        return as_json(client._request("GET", f"/api/github/rate-limit/{account_label}"))

    # ── Triage Prompts ──────────────────────────────────────────────

    @mcp.tool()
    def github_get_triage_prompts(repo: str = "") -> str:
        """Get triage prompts for issue/PR/discussion."""
        params = {}
        if repo:
            params["repo"] = repo
        return as_json(client._request("GET", "/api/github/triage-prompts", params=params))

    @mcp.tool()
    def github_save_triage_prompts(issue: str = "", pr: str = "", discussion: str = "", repo: str = "") -> str:
        """Update triage prompts (global or per-repo)."""
        body = {}
        if repo:
            body["repo"] = repo
            if issue is not None:
                body["issue"] = issue
            if pr is not None:
                body["pr"] = pr
            if discussion is not None:
                body["discussion"] = discussion
        else:
            if issue:
                body["issue"] = issue
            if pr:
                body["pr"] = pr
            if discussion:
                body["discussion"] = discussion
        if not body:
            return as_json({"error": "At least one prompt must be provided"})
        return as_json(client._request("PUT", "/api/github/triage-prompts", body=body))
