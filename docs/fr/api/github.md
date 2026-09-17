# GitHub Integration API

APIs for GitHub account management, issues, pull requests, notifications, and releases.

Provided by the `builtin-github` extension. All endpoints require authentication (PIN session or API Key).

## Account Management

### GET /api/github/accounts

List registered GitHub accounts. Tokens are masked in the response.

### Réponse

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

Register a new GitHub account.

### Requête

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `label` | string | Yes | Unique account identifier label |
| `token` | string | Yes | GitHub Personal Access Token |
| `repos` | string[] | Yes | Repositories to monitor (`owner/repo` format) |

### Réponse

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

Update an existing account's paramètres.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |

### Requête

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `token` | string | No | New token value |
| `repos` | string[] | No | Updated repository list |
| `enabled` | boolean | No | Activer or disable the account |

### DELETE /api/github/accounts/<label>

Remove an account.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |

---

## Issues

### GET /api/github/issues/<label>

Fetch issues from the account's repositories.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |
| `state` | string | Issue state filter (`open`, `closed`, `all`) |
| `labels` | string | Label filter (comma-separated) |
| `since` | string | Issues updated after this date (ISO 8601) |
| `repo` | string | Filter to a specific repository (`owner/repo`) |

### curl Example

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

Créer un nouveau issue.

### Requête

```json
{
  "repo": "owner/repo1",
  "title": "Bug: crash on login screen",
  "body": "Steps to reproduce:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `repo` | string | Yes | Target repository (`owner/repo`) |
| `title` | string | Yes | Issue title |
| `body` | string | No | Issue body (Markdown) |
| `labels` | string[] | No | Labels to apply |

### GET /api/github/issue/<label>/<repo>/<number>

Retrieve issue details including comments.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label |
| `repo` | string | Repository name (`owner/repo`) |
| `number` | int | Issue number |

### POST /api/github/triage/<label>

Run issue triage (classification and prioritization).

### Requête

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `state` | string | No | State filter for target issues |
| `since` | string | No | Only triage issues updated after this date (ISO 8601) |

---

## Pull Requêtes

### GET /api/github/pulls/<label>

List pull requests.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |
| `state` | string | PR state (`open`, `closed`, `all`) |
| `repo` | string | Filter to a specific repository (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

Retrieve PR details including changed files.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label |
| `repo` | string | Repository name (`owner/repo`) |
| `number` | int | PR number |

---

## Notifications

### GET /api/github/notifications/<label>

List notifications.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |
| `all` | string | Set to `true` to include read notifications (default: unread only) |

### PATCH /api/github/notifications/<label>/<thread_id>

Mark a specific notification thread as read.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label |
| `thread_id` | string | Notification thread ID |

### POST /api/github/notifications/<label>/mark-all-read

Mark all notifications as read.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |

---

## Discussions

### GET /api/github/discussions/<label>

Fetch GitHub Discussions (via GraphQL API).

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |
| `repo` | string | Filter to a specific repository (`owner/repo`) |

---

## Releases

### GET /api/github/releases/<label>

List releases.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |
| `repo` | string | Filter to a specific repository (`owner/repo`) |

---

## Repository Stats

### GET /api/github/repo-stats/<label>/<repo>

Retrieve statistics for a single repository.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label |
| `repo` | string | Repository name (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

Retrieve statistics for all registered repositories at once.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |

---

## Rate Limit

### GET /api/github/rate-limit/<label>

Check GitHub API rate limit status.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `label` | string | Account label (path parameter) |

### Réponse Example

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## Triage Prompts

### GET /api/github/triage-prompts

Get editable triage prompts for issue/PR/discussion, along with their default values.

### Réponse

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

Update triage prompts. Only provided fields are updated.

### Requête

```json
{
  "issue": "Custom issue triage prompt...",
  "pr": "Custom PR prompt...",
  "discussion": "Custom discussion prompt..."
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `issue` | string | No | Triage prompt for issues |
| `pr` | string | No | Triage prompt for pull requests |
| `discussion` | string | No | Triage prompt for discussions |

---

## Issue Queue

### GET /api/github/queue

Get issue queue items with optional status filter.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter: `pending`, `notified`, `dismissed`, or empty for all |
| `limit` | int | Max results (default 50, max 200) |

### Réponse

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug report title",
        "body": "Issue body...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

Get pending (unread) issues for MCP notification.

### Réponse

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

Set triage result for a queue item.

### Requête

```json
{ "result": "valid" }
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `result` | string | Yes | `valid` or `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

Dismiss a queue item. Optionally auto-close the issue on GitHub.

### Requête

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `auto_close` | boolean | No | Close the issue on GitHub with a template comment |
| `account_label` | string | No | Requis if `auto_close` is true |

### PUT /api/github/queue/<queue_id>/status

Update queue item status.

### Requête

```json
{ "status": "notified" }
```

| Champ | Type | Requis | Description |
|-------|------|----------|-------------|
| `status` | string | Yes | `pending`, `notified`, or `dismissed` |

### GET /api/github/queue/config

Get issue queue configuration.

### Réponse

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Update issue queue configuration.

### Requête

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

Trigger immediate polling of all accounts for new issues.

---

## WebUI

### GET /ext/github

GitHub Integration WebUI page. Access directly in the browser.

Requires an authenticated PIN session.
