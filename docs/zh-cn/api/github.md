# GitHub Integration API

用于 GitHub 账号管理、Issues、Pull Requests、通知及 Releases 的 API。

由 `builtin-github` 扩展提供。所有端点均需要认证（PIN 会话或 API Key）。

## 账号管理

### GET /api/github/accounts

列出已注册的 GitHub 账号。响应中的令牌会以掩码方式显示。

### 响应

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

注册新的 GitHub 账号。

### 请求

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `label` | string | 是 | 唯一的账号标识标签 |
| `token` | string | 是 | GitHub Personal Access Token |
| `repos` | string[] | 是 | 要监控的仓库（`owner/repo` 格式） |

### 响应

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

更新现有账号的设置。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |

### 请求

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `token` | string | 否 | 新的令牌值 |
| `repos` | string[] | 否 | 更新后的仓库列表 |
| `enabled` | boolean | 否 | 启用或禁用账号 |

### DELETE /api/github/accounts/<label>

移除账号。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |

---

## Issues

### GET /api/github/issues/<label>

从账号的仓库中获取 Issues。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |
| `state` | string | Issue 状态筛选（`open`、`closed`、`all`） |
| `labels` | string | 标签筛选（以逗号分隔） |
| `since` | string | 仅获取在此日期之后更新的 Issues（ISO 8601） |
| `repo` | string | 筛选特定仓库 |

### curl 示例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

创建新的 Issue。

### 请求

```json
{
  "repo": "owner/repo1",
  "title": "Bug: 登录界面崩溃",
  "body": "复现步骤:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `repo` | string | 是 | 目标仓库（`owner/repo`） |
| `title` | string | 是 | Issue 标题 |
| `body` | string | 否 | Issue 正文（Markdown） |
| `labels` | string[] | 否 | 要应用的标签 |

### GET /api/github/issue/<label>/<repo>/<number>

获取 Issue 详细信息，包括评论。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签 |
| `repo` | string | 仓库名称（`owner/repo`） |
| `number` | int | Issue 编号 |

### POST /api/github/triage/<label>

运行 Issue 分类筛选（分类与优先级排序）。

### 请求

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `state` | string | 否 | 目标 Issues 的状态筛选 |
| `since` | string | 否 | 仅分类在此日期之后更新的 Issues（ISO 8601） |

---

## Pull Requests

### GET /api/github/pulls/<label>

列出 Pull Requests。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |
| `state` | string | PR 状态（`open`、`closed`、`all`） |
| `repo` | string | 筛选特定仓库 |

### GET /api/github/pull/<label>/<repo>/<number>

获取 PR 详细信息，包括变更的文件。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签 |
| `repo` | string | 仓库名称（`owner/repo`） |
| `number` | int | PR 编号 |

---

## 通知

### GET /api/github/notifications/<label>

列出通知。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |
| `all` | string | 设为 `true` 以包含已读通知（默认：仅未读） |

### PATCH /api/github/notifications/<label>/<thread_id>

将特定通知线程标记为已读。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签 |
| `thread_id` | string | 通知线程 ID |

### POST /api/github/notifications/<label>/mark-all-read

将所有通知标记为已读。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |

---

## Discussions

### GET /api/github/discussions/<label>

获取 GitHub Discussions（通过 GraphQL API）。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |
| `repo` | string | 筛选特定仓库（`owner/repo`） |

---

## Releases

### GET /api/github/releases/<label>

列出 Releases。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |
| `repo` | string | 筛选特定仓库（`owner/repo`） |

---

## 仓库统计

### GET /api/github/repo-stats/<label>/<repo>

获取单个仓库的统计数据。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签 |
| `repo` | string | 仓库名称（`owner/repo`） |

### GET /api/github/repo-stats-all/<label>

一次获取所有已注册仓库的统计数据。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |

---

## 速率限制

### GET /api/github/rate-limit/<label>

检查 GitHub API 速率限制状态。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `label` | string | 账号标签（路径参数） |

### 响应示例

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

## 分类提示词

### GET /api/github/triage-prompts

获取 Issue/PR/Discussion 的可编辑分类提示词及其默认值。

### 响应

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

更新分类提示词。仅更新提供的字段。

### 请求

```json
{
  "issue": "自定义 Issue 分类提示词...",
  "pr": "自定义 PR 提示词...",
  "discussion": "自定义 Discussion 提示词..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `issue` | string | 否 | Issue 分类提示词 |
| `pr` | string | 否 | Pull Request 分类提示词 |
| `discussion` | string | 否 | Discussion 分类提示词 |

---

## Issue 队列

### GET /api/github/queue

通过可选的状态筛选获取 Issue 队列项目。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 筛选: `pending`、`notified`、`dismissed`，或留空获取全部 |
| `limit` | int | 最大结果数（默认 50，最大 200） |

### 响应

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug 报告标题",
        "body": "Issue 正文...",
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

获取用于 MCP 通知的待处理（未读）Issue。

### 响应

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

设置队列项目的分类结果。

### 请求

```json
{ "result": "valid" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `result` | string | 是 | `valid` 或 `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

驳回队列项目。可选择在 GitHub 上自动关闭 Issue。

### 请求

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `auto_close` | boolean | 否 | 使用模板评论在 GitHub 上关闭 Issue |
| `account_label` | string | 否 | 当 `auto_close` 为 true 时必填 |

### PUT /api/github/queue/<queue_id>/status

更新队列项目状态。

### 请求

```json
{ "status": "notified" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 是 | `pending`、`notified` 或 `dismissed` |

### GET /api/github/queue/config

获取 Issue 队列配置。

### 响应

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

更新 Issue 队列配置。

### 请求

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

立即轮询所有账号的新 Issue。

---

## WebUI

### GET /ext/github

GitHub Integration WebUI 页面。可直接在浏览器中访问。需要已认证的 PIN 会话。
