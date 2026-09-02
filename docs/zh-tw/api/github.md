# GitHub Integration API

用於 GitHub 帳號管理、Issues、Pull Requests、通知及 Releases 的 API。

由 `builtin-github` 擴充套件提供。所有端點皆需要驗證（PIN 工作階段或 API Key）。

## 帳號管理

### GET /api/github/accounts

列出已註冊的 GitHub 帳號。回應中的權杖會以遮罩方式顯示。

### 回應

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

註冊新的 GitHub 帳號。

### 請求

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `label` | string | 是 | 唯一的帳號識別標籤 |
| `token` | string | 是 | GitHub Personal Access Token |
| `repos` | string[] | 是 | 要監控的儲存庫（`owner/repo` 格式） |

### 回應

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

更新現有帳號的設定。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |

### 請求

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `token` | string | 否 | 新的權杖值 |
| `repos` | string[] | 否 | 更新後的儲存庫清單 |
| `enabled` | boolean | 否 | 啟用或停用帳號 |

### DELETE /api/github/accounts/<label>

移除帳號。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |

---

## Issues

### GET /api/github/issues/<label>

從帳號的儲存庫中取得 Issues。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |
| `state` | string | Issue 狀態篩選（`open`、`closed`、`all`） |
| `labels` | string | 標籤篩選（以逗號分隔） |
| `since` | string | 僅取得在此日期之後更新的 Issues（ISO 8601） |
| `repo` | string | 篩選特定儲存庫 |

### curl 範例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

建立新的 Issue。

### 請求

```json
{
  "repo": "owner/repo1",
  "title": "Bug: 登入畫面當機",
  "body": "重現步驟:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `repo` | string | 是 | 目標儲存庫（`owner/repo`） |
| `title` | string | 是 | Issue 標題 |
| `body` | string | 否 | Issue 內文（Markdown） |
| `labels` | string[] | 否 | 要套用的標籤 |

### GET /api/github/issue/<label>/<repo>/<number>

取得 Issue 詳細資訊，包括留言。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤 |
| `repo` | string | 儲存庫名稱（`owner/repo`） |
| `number` | int | Issue 編號 |

### POST /api/github/triage/<label>

執行 Issue 分類篩選（分類與優先排序）。

### 請求

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `state` | string | 否 | 目標 Issues 的狀態篩選 |
| `since` | string | 否 | 僅分類在此日期之後更新的 Issues（ISO 8601） |

---

## Pull Requests

### GET /api/github/pulls/<label>

列出 Pull Requests。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |
| `state` | string | PR 狀態（`open`、`closed`、`all`） |
| `repo` | string | 篩選特定儲存庫 |

### GET /api/github/pull/<label>/<repo>/<number>

取得 PR 詳細資訊，包括變更的檔案。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤 |
| `repo` | string | 儲存庫名稱（`owner/repo`） |
| `number` | int | PR 編號 |

---

## 通知

### GET /api/github/notifications/<label>

列出通知。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |
| `all` | string | 設為 `true` 以包含已讀通知（預設：僅未讀） |

### PATCH /api/github/notifications/<label>/<thread_id>

將特定通知執行緒標記為已讀。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤 |
| `thread_id` | string | 通知執行緒 ID |

### POST /api/github/notifications/<label>/mark-all-read

將所有通知標記為已讀。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |

---

## Discussions

### GET /api/github/discussions/<label>

取得 GitHub Discussions（透過 GraphQL API）。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |
| `repo` | string | 篩選特定儲存庫（`owner/repo`） |

---

## Releases

### GET /api/github/releases/<label>

列出 Releases。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |
| `repo` | string | 篩選特定儲存庫（`owner/repo`） |

---

## 儲存庫統計

### GET /api/github/repo-stats/<label>/<repo>

取得單一儲存庫的統計資料。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤 |
| `repo` | string | 儲存庫名稱（`owner/repo`） |

### GET /api/github/repo-stats-all/<label>

一次取得所有已註冊儲存庫的統計資料。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |

---

## 速率限制

### GET /api/github/rate-limit/<label>

檢查 GitHub API 速率限制狀態。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `label` | string | 帳號標籤（路徑參數） |

### 回應範例

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

## 分類提示詞

### GET /api/github/triage-prompts

取得 Issue/PR/Discussion 的可編輯分類提示詞及其預設值。

### 回應

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

更新分類提示詞。僅更新提供的欄位。

### 請求

```json
{
  "issue": "自訂 Issue 分類提示詞...",
  "pr": "自訂 PR 提示詞...",
  "discussion": "自訂 Discussion 提示詞..."
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `issue` | string | 否 | Issue 分類提示詞 |
| `pr` | string | 否 | Pull Request 分類提示詞 |
| `discussion` | string | 否 | Discussion 分類提示詞 |

---

## Issue 佇列

### GET /api/github/queue

透過可選的狀態篩選取得 Issue 佇列項目。

### 參數

| 參數 | 型別 | 說明 |
|------|------|------|
| `status` | string | 篩選: `pending`、`notified`、`dismissed`，或留空取得全部 |
| `limit` | int | 最大結果數（預設 50，最大 200） |

### 回應

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "Bug 報告標題",
        "body": "Issue 內文...",
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

取得用於 MCP 通知的待處理（未讀）Issue。

### 回應

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

設定佇列項目的分類結果。

### 請求

```json
{ "result": "valid" }
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `result` | string | 是 | `valid` 或 `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

駁回佇列項目。可選擇在 GitHub 上自動關閉 Issue。

### 請求

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `auto_close` | boolean | 否 | 使用範本留言在 GitHub 上關閉 Issue |
| `account_label` | string | 否 | 當 `auto_close` 為 true 時必填 |

### PUT /api/github/queue/<queue_id>/status

更新佇列項目狀態。

### 請求

```json
{ "status": "notified" }
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `status` | string | 是 | `pending`、`notified` 或 `dismissed` |

### GET /api/github/queue/config

取得 Issue 佇列設定。

### 回應

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

更新 Issue 佇列設定。

### 請求

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

立即輪詢所有帳號的新 Issue。

---

## WebUI

### GET /ext/github

GitHub Integration WebUI 頁面。可直接在瀏覽器中存取。需要已驗證的 PIN 工作階段。
