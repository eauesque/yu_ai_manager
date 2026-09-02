# GitHub Integration

## Overview

GitHub Integration lets you manage GitHub repositories, issues, pull requests, discussions, and releases directly from YU AI Manager. It supports multiple GitHub accounts with encrypted token storage, provides a dashboard with notifications and repository statistics, and includes AI-powered issue triage.

## Setup

### Obtaining a GitHub Personal Access Token (PAT)

1. Log in to GitHub and navigate to **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Click **Generate new token (classic)**
3. Enter a token name and set an expiration period
4. Under scopes, check **`repo`** (required for full repository access)
5. Click **Generate token** and copy the displayed token

> **Important**: The token is only shown once. Make sure to copy it before leaving the page.

### Adding an Account

1. Open the Extensions launcher and click the **GitHub** card, or navigate directly to `/ext/github`
2. Go to the **Settings** tab
3. Click **Add Account**
4. Fill in the following:
   - **Label**: A display name for the account (e.g., "Personal", "Work")
   - **Token**: The PAT obtained above
   - **Repositories**: Repositories to watch in `owner/repo` format (multiple allowed)
5. After saving, select the account from the dropdown

## Features

### Dashboard

The dashboard loads automatically when you select an account.

- **Notifications**: Lists unread GitHub notifications
- **Repository Stats**: Displays star count, fork count, and open issue count as summary cards
- **Summary Cards**: Quick overview of all watched repositories

### Issues

- Filter by repository and state (open/closed)
- View issue details including body, comments, and labels
- Create new issues
- **Triage**: AI-powered automatic classification
  - `valid_bug` — Confirmed bug report
  - `needs_info` — Requires additional information
  - `skip` — No action needed
- **Issue Queue**: Automatically polls GitHub for new issues and queues them locally. When an MCP client (Claude Desktop) connects, pending issues are notified in batch.

### Pull Requests

- List and filter pull requests
- View diff statistics (lines added/removed, files changed)
- Detail view with per-file change diffs

### Discussions

- Fetch discussion lists via the GraphQL API
- Category badges and answered status indicators

### Releases

- View the latest releases from watched repositories
- Read release notes

### Settings

- Add, edit, delete, and enable/disable accounts
- View API rate limit status
- Configure language filter and schedule interval
- Configure issue queue polling interval, auto-close for invalid issues, and MCP connection notifications
- Edit triage prompts for issues, PRs, and discussions (see [Examples](/help/github-triage-examples))

### Issue Queue

The issue queue polls GitHub periodically and stores new issues locally.

- **Polling**: Runs automatically via the scheduler (configurable interval, default 60 minutes)
- **Notification**: On MCP connection, pending issues are reported to Claude Desktop
- **Triage**: Each queued issue can be triaged as valid or invalid
- **Auto-close**: Invalid issues can be automatically closed on GitHub with a template comment
- **Manual poll**: Click "Poll Now" in Settings to fetch immediately

### Triage Prompts

Customize the AI instructions used when triaging issues, PRs, and discussions.

- Each type (issue, PR, discussion) has its own editable prompt
- Default prompts are provided and can be restored with "Reset to Default"
- See [Triage Prompt Examples](/help/github-triage-examples) for templates in multiple languages and styles
- Prompts are stored in config.json (not encrypted, as they contain no secrets)

## MCP Integration

GitHub Integration provides 12 MCP tools for use with Claude Code:

- List and view issues
- List and view pull requests
- Fetch notifications
- Get and update triage prompts
- Manage issue queue (pending, triage, dismiss, poll)

MCP tools let you access GitHub information without leaving your editor during development.

## Tips

- **Multiple accounts**: Separate personal and work accounts for cleaner management
- **Token scopes**: The `repo` scope covers all core features. For private organization repositories, you may also need to authorize SSO for the organization
- **Triage**: Use the triage feature on repositories with many issues to automatically prioritize them
- **Rate limits**: GitHub API has hourly request limits. Check remaining quota in the Settings tab
- **Token security**: Tokens are encrypted at rest on the server. They are never stored in plain text
- **Dashboard refresh**: Data is automatically reloaded when you switch accounts
