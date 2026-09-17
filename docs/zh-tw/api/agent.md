# Agent Safety Gateway API

管理 AI 代理安全控制的 API。提供 Kill Switch、Circuit Breaker、Budget、Action Journal、Approval Gate、Scope Fence、Auto-Approve、Tool Classification、Undo、Anomaly Detection 及 Audit Bureau 功能。

所有 POST/DELETE 端點需要 `X-Requested-With` 標頭（使用 Bearer API Key 時除外）。

---

## Kill Switch

### POST /api/agent/kill

啟動 Kill Switch，立即停止所有代理操作。

#### Rate Limit

WRITE

#### 請求

```json
{
  "reason": "Manual kill via API"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `reason` | string | 否 | 停止原因。預設為 `"Manual kill via API"` |

#### 回應

```json
{
  "ok": true,
  "status": {
    "killed": true,
    "reason": "Manual kill via API",
    "killed_at": "2026-03-22T12:00:00"
  }
}
```

### POST /api/agent/resume

解除 Kill Switch，恢復代理操作。

#### Rate Limit

WRITE

#### 請求

無（空主體）

#### 回應

```json
{
  "ok": true,
  "status": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  }
}
```

### GET /api/agent/status

取得 Kill Switch、Circuit Breaker 和 Budget 的統一狀態。

#### 參數

無

#### 回應

```json
{
  "kill_switch": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  },
  "circuit_breaker": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  },
  "budget": {
    "session_id": "abc123",
    "used": 10,
    "limit": 100,
    "remaining": 90
  },
  "killed": false,
  "reason": "",
  "killed_at": ""
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `kill_switch` | object | Kill Switch 詳細狀態 |
| `circuit_breaker` | object | Circuit Breaker 詳細狀態。錯誤時回傳 `{"enabled": false, "state": "unknown"}` |
| `budget` | object | Budget 詳細狀態。錯誤時回傳空物件 |
| `killed` | boolean | Kill Switch 啟動旗標（頂層，向下相容） |
| `reason` | string | Kill Switch 原因（向下相容） |
| `killed_at` | string | Kill Switch 啟動時間（向下相容） |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

取得 Circuit Breaker 狀態。

#### 參數

無

#### 回應

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `enabled` | boolean | Circuit Breaker 是否啟用 |
| `state` | string | 狀態：`"closed"`（正常）、`"open"`（已觸發）、`"half_open"`（探測中） |
| `failure_count` | int | 連續失敗次數 |
| `threshold` | int | 觸發開啟的失敗次數閾值 |

### POST /api/agent/circuit-breaker/reset

將 Circuit Breaker 重設為 closed 狀態。

#### Rate Limit

WRITE

#### 請求

無（空主體）

#### 回應

```json
{
  "ok": true,
  "status": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  }
}
```

---

## Budget

### GET /api/agent/budget

取得目前工作階段的剩餘預算。

#### 參數

無

#### 回應

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `session_id` | string | 工作階段 ID |
| `used` | int | 已消耗的操作數 |
| `limit` | int | 允許的最大操作數 |
| `remaining` | int | 剩餘操作數 |

### POST /api/agent/budget/reset

重設預算計數器。

#### Rate Limit

WRITE

#### 請求

無（空主體）

#### 回應

```json
{
  "ok": true,
  "status": {
    "session_id": "abc123",
    "used": 0,
    "limit": 100,
    "remaining": 100
  }
}
```

---

## Action Journal

### GET /api/agent/journal

搜尋 Action Journal。回傳代理執行的操作歷史記錄。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `tool_name` | string | 否 | 依工具名稱篩選 |
| `status` | string | 否 | 依狀態篩選 |
| `session_id` | string | 否 | 依工作階段 ID 篩選 |
| `limit` | int | 否 | 最大結果數（預設：50，最大：200） |
| `offset` | int | 否 | 偏移量（預設：0） |

#### 回應

```json
{
  "entries": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "status": "completed",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "result": {"ok": true},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "total": 1
}
```

### GET /api/agent/journal/stats

取得 Action Journal 統計資訊。

#### 參數

無

#### 回應

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Approval Gate

### GET /api/agent/approval

取得待核准的請求清單。

#### 參數

無

#### 回應

```json
{
  "pending": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "params": {},
      "requested_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/agent/approval/\<request_id\>

回覆核准請求。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `request_id` | string | 請求 ID（路徑參數） |

#### 請求

```json
{
  "decision": "allow"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `decision` | string | 是 | `"allow"`（允許）、`"deny"`（拒絕）、`"always_allow"`（永遠允許） |

#### 回應

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### 錯誤

- `400`：`decision` 不是 `allow`/`deny`/`always_allow` 之一
- `404`：請求未找到或已回覆

### GET /api/agent/approval/history

取得核准歷史記錄。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 最大結果數（預設：50，最大：200） |

#### 回應

```json
{
  "history": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "decision": "allow",
      "decided_at": "2026-03-22T12:01:00"
    }
  ]
}
```

---

## Scope Fence

### GET /api/agent/scope

取得所有工作階段的 Scope Fence 狀態。

#### 參數

無

#### 回應

```json
{
  "sessions": {
    "abc123": {
      "preset": "tagger",
      "denied": ["purge_deleted", "hard_delete"],
      "name": "Tagger Bot",
      "expires_at": "2026-03-22T14:00:00"
    }
  },
  "count": 1
}
```

### GET /api/agent/scope/\<session_id\>

取得特定工作階段的 scope。

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `session_id` | string | 工作階段 ID（路徑參數） |

#### 回應

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### 錯誤

- `404`：找不到工作階段 scope

### POST /api/agent/scope/\<session_id\>

設定工作階段 scope。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `session_id` | string | 工作階段 ID（路徑參數） |

#### 請求

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `preset` | string | 否 | 預設名稱：`"read_only"`、`"tagger"`、`"organizer"`、`"full_access"` |
| `denied` | string[] | 否 | 拒絕的工具名稱清單 |
| `name` | string | 否 | scope 的顯示名稱 |
| `duration_hours` | number | 否 | scope 過期時間（小時） |

#### 回應

```json
{
  "ok": true,
  "scope": {
    "preset": "tagger",
    "denied": ["purge_deleted"],
    "name": "Tagger Bot",
    "expires_at": "2026-03-22T14:00:00"
  }
}
```

#### 錯誤

- `400`：`denied` 不是清單

### DELETE /api/agent/scope/\<session_id\>

刪除工作階段 scope。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `session_id` | string | 工作階段 ID（路徑參數） |

#### 回應

```json
{
  "ok": true
}
```

---

## Auto-Approve 規則

### GET /api/agent/auto-approve

取得 Auto-Approve 規則清單。

#### 參數

無

#### 回應

```json
{
  "rules": [
    {
      "index": 0,
      "tool": "add_tags",
      "conditions": {"max_count": 10}
    }
  ]
}
```

### POST /api/agent/auto-approve

新增 Auto-Approve 規則。

#### Rate Limit

WRITE

#### 請求

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `tool` | string | 是 | 目標工具名稱 |
| `conditions` | object | 否 | 自動核准的條件。省略表示無條件核准 |

#### 回應

```json
{
  "ok": true,
  "rule": {
    "index": 1,
    "tool": "add_tags",
    "conditions": {"max_count": 10}
  }
}
```

#### 錯誤

- `400`：未指定 `tool`
- `400`：`conditions` 不是字典

### DELETE /api/agent/auto-approve/\<index\>

刪除 Auto-Approve 規則。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `index` | int | 規則索引（路徑參數） |

#### 回應

```json
{
  "ok": true
}
```

#### 錯誤

- `404`：找不到規則

---

## Tool Classification

### GET /api/agent/tool-levels

取得工具分級資訊。指定 `tool` 參數時回傳該工具的等級，否則回傳所有工具的摘要和自訂覆寫。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `tool` | string | 否 | 工具名稱。指定時僅回傳該工具的等級 |

#### 回應（特定工具）

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### 回應（所有工具）

```json
{
  "summary": {
    "safe": ["list_files", "search_files"],
    "write": ["add_tags", "remove_tags"],
    "destructive": ["purge_deleted", "hard_delete"]
  },
  "overrides": {
    "custom_tool": "safe"
  }
}
```

---

## Undo

### POST /api/agent/undo/\<journal_id\>

復原已記錄的操作。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `journal_id` | int | Journal 項目 ID（路徑參數） |

#### 回應

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### 錯誤

- `400`：復原失敗（操作不可復原、已復原等）

### GET /api/agent/undoable

取得可復原的操作清單。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `session_id` | string | 否 | 依工作階段 ID 篩選 |
| `limit` | int | 否 | 最大結果數（預設：50，最大：200） |

#### 回應

```json
{
  "items": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

---

## Anomaly Detection

### GET /api/agent/anomaly

取得 Anomaly Detection 狀態。

#### 參數

無

#### 回應

```json
{
  "enabled": true,
  "window_minutes": 10,
  "thresholds": {
    "max_actions_per_window": 100,
    "max_errors_per_window": 20
  },
  "current": {
    "actions": 15,
    "errors": 0
  }
}
```

### GET /api/agent/anomaly/alerts

取得 Anomaly Detection 警示。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 最大結果數（預設：50，最大：200） |

#### 回應

```json
{
  "alerts": [
    {
      "id": 1,
      "type": "high_error_rate",
      "message": "Error rate exceeded threshold",
      "severity": "warning",
      "created_at": "2026-03-22T12:00:00"
    }
  ]
}
```

### POST /api/agent/anomaly/reset

重設 Anomaly Detection 歷史記錄和警示。

#### Rate Limit

WRITE

#### 請求

無（空主體）

#### 回應

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

取得 Audit Bureau 狀態。

#### 參數

無

#### 回應

```json
{
  "data": {
    "total_entries": 500,
    "unacknowledged": 3,
    "last_report_at": "2026-03-22T00:00:00"
  }
}
```

### GET /api/agent/audit/log

搜尋 Audit Log。

#### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `event_type` | string | 否 | 依事件類型篩選 |
| `severity` | string | 否 | 依嚴重程度篩選 |
| `source` | string | 否 | 依來源篩選 |
| `unacknowledged` | string | 否 | 設為 `"1"` 或 `"true"` 僅回傳未確認的項目 |
| `limit` | int | 否 | 最大結果數（預設：50，最大：200） |
| `offset` | int | 否 | 偏移量（預設：0） |

#### 回應

```json
{
  "data": {
    "entries": [
      {
        "id": 1,
        "event_type": "kill_switch_activated",
        "severity": "critical",
        "source": "api",
        "message": "Kill switch activated: Manual kill via API",
        "acknowledged": false,
        "created_at": "2026-03-22T12:00:00"
      }
    ],
    "total": 1
  }
}
```

### POST /api/agent/audit/acknowledge/\<audit_id\>

將 Audit Log 項目標記為使用者已確認。

#### Rate Limit

WRITE

#### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `audit_id` | int | Audit Log 項目 ID（路徑參數） |

#### 回應

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### 錯誤

- `404`：找不到項目或已確認

### POST /api/agent/audit/report

手動產生 Audit Bureau 定期報告。

#### Rate Limit

WRITE

#### 請求

```json
{
  "hours": 24
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `hours` | int | 否 | 報告期間（小時）。預設：24，最大：720 |

#### 回應

```json
{
  "data": {
    "period_hours": 24,
    "total_events": 150,
    "by_severity": {"critical": 2, "warning": 10, "info": 138},
    "by_type": {"kill_switch_activated": 2, "approval_denied": 5},
    "generated_at": "2026-03-22T12:00:00"
  }
}
```
