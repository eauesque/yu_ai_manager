# Agent Safety Gateway API

管理 AI 代理安全控制的 API。提供 Kill Switch、Circuit Breaker、Budget、Action Journal、Approval Gate、Scope Fence、Auto-Approve、Tool Classification、Undo、Anomaly Detection 及 Audit Bureau 功能。

所有 POST/DELETE 端点需要 `X-Requested-With` 标头（使用 Bearer API Key 时除外）。

---

## Kill Switch

### POST /api/agent/kill

启动 Kill Switch，立即停止所有代理操作。

#### Rate Limit

WRITE

#### 请求

```json
{
  "reason": "Manual kill via API"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `reason` | string | 否 | 停止原因。默认为 `"Manual kill via API"` |

#### 响应

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

解除 Kill Switch，恢复代理操作。

#### Rate Limit

WRITE

#### 请求

无（空主体）

#### 响应

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

获取 Kill Switch、Circuit Breaker 和 Budget 的统一状态。

#### 参数

无

#### 响应

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

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `kill_switch` | object | Kill Switch 详细状态 |
| `circuit_breaker` | object | Circuit Breaker 详细状态。错误时返回 `{"enabled": false, "state": "unknown"}` |
| `budget` | object | Budget 详细状态。错误时返回空对象 |
| `killed` | boolean | Kill Switch 激活标志（顶层，向下兼容） |
| `reason` | string | Kill Switch 原因（向下兼容） |
| `killed_at` | string | Kill Switch 激活时间（向下兼容） |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

获取 Circuit Breaker 状态。

#### 参数

无

#### 响应

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `enabled` | boolean | Circuit Breaker 是否启用 |
| `state` | string | 状态：`"closed"`（正常）、`"open"`（已触发）、`"half_open"`（探测中） |
| `failure_count` | int | 连续失败次数 |
| `threshold` | int | 触发开启的失败次数阈值 |

### POST /api/agent/circuit-breaker/reset

将 Circuit Breaker 重置为 closed 状态。

#### Rate Limit

WRITE

#### 请求

无（空主体）

#### 响应

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

获取当前会话的剩余预算。

#### 参数

无

#### 响应

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `session_id` | string | 会话 ID |
| `used` | int | 已消耗的操作数 |
| `limit` | int | 允许的最大操作数 |
| `remaining` | int | 剩余操作数 |

### POST /api/agent/budget/reset

重置预算计数器。

#### Rate Limit

WRITE

#### 请求

无（空主体）

#### 响应

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

搜索 Action Journal。返回代理执行的操作历史记录。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `tool_name` | string | 否 | 按工具名称筛选 |
| `status` | string | 否 | 按状态筛选 |
| `session_id` | string | 否 | 按会话 ID 筛选 |
| `limit` | int | 否 | 最大结果数（默认：50，最大：200） |
| `offset` | int | 否 | 偏移量（默认：0） |

#### 响应

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

获取 Action Journal 统计信息。

#### 参数

无

#### 响应

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

获取待审批的请求列表。

#### 参数

无

#### 响应

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

回复审批请求。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `request_id` | string | 请求 ID（路径参数） |

#### 请求

```json
{
  "decision": "allow"
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `decision` | string | 是 | `"allow"`（允许）、`"deny"`（拒绝）、`"always_allow"`（永远允许） |

#### 响应

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### 错误

- `400`：`decision` 不是 `allow`/`deny`/`always_allow` 之一
- `404`：请求未找到或已回复

### GET /api/agent/approval/history

获取审批历史记录。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 最大结果数（默认：50，最大：200） |

#### 响应

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

获取所有会话的 Scope Fence 状态。

#### 参数

无

#### 响应

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

获取特定会话的 scope。

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `session_id` | string | 会话 ID（路径参数） |

#### 响应

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### 错误

- `404`：找不到会话 scope

### POST /api/agent/scope/\<session_id\>

设置会话 scope。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `session_id` | string | 会话 ID（路径参数） |

#### 请求

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `preset` | string | 否 | 预设名称：`"read_only"`、`"tagger"`、`"organizer"`、`"full_access"` |
| `denied` | string[] | 否 | 拒绝的工具名称列表 |
| `name` | string | 否 | scope 的显示名称 |
| `duration_hours` | number | 否 | scope 过期时间（小时） |

#### 响应

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

#### 错误

- `400`：`denied` 不是列表

### DELETE /api/agent/scope/\<session_id\>

删除会话 scope。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `session_id` | string | 会话 ID（路径参数） |

#### 响应

```json
{
  "ok": true
}
```

---

## Auto-Approve 规则

### GET /api/agent/auto-approve

获取 Auto-Approve 规则列表。

#### 参数

无

#### 响应

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

添加 Auto-Approve 规则。

#### Rate Limit

WRITE

#### 请求

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `tool` | string | 是 | 目标工具名称 |
| `conditions` | object | 否 | 自动审批的条件。省略表示无条件审批 |

#### 响应

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

#### 错误

- `400`：未指定 `tool`
- `400`：`conditions` 不是字典

### DELETE /api/agent/auto-approve/\<index\>

删除 Auto-Approve 规则。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `index` | int | 规则索引（路径参数） |

#### 响应

```json
{
  "ok": true
}
```

#### 错误

- `404`：找不到规则

---

## Tool Classification

### GET /api/agent/tool-levels

获取工具分级信息。指定 `tool` 参数时返回该工具的等级，否则返回所有工具的摘要和自定义覆盖。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `tool` | string | 否 | 工具名称。指定时仅返回该工具的等级 |

#### 响应（特定工具）

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### 响应（所有工具）

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

撤销已记录的操作。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `journal_id` | int | Journal 条目 ID（路径参数） |

#### 响应

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### 错误

- `400`：撤销失败（操作不可撤销、已撤销等）

### GET /api/agent/undoable

获取可撤销的操作列表。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `session_id` | string | 否 | 按会话 ID 筛选 |
| `limit` | int | 否 | 最大结果数（默认：50，最大：200） |

#### 响应

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

获取 Anomaly Detection 状态。

#### 参数

无

#### 响应

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

获取 Anomaly Detection 警报。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `limit` | int | 否 | 最大结果数（默认：50，最大：200） |

#### 响应

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

重置 Anomaly Detection 历史记录和警报。

#### Rate Limit

WRITE

#### 请求

无（空主体）

#### 响应

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

获取 Audit Bureau 状态。

#### 参数

无

#### 响应

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

搜索 Audit Log。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `event_type` | string | 否 | 按事件类型筛选 |
| `severity` | string | 否 | 按严重程度筛选 |
| `source` | string | 否 | 按来源筛选 |
| `unacknowledged` | string | 否 | 设为 `"1"` 或 `"true"` 仅返回未确认的条目 |
| `limit` | int | 否 | 最大结果数（默认：50，最大：200） |
| `offset` | int | 否 | 偏移量（默认：0） |

#### 响应

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

将 Audit Log 条目标记为用户已确认。

#### Rate Limit

WRITE

#### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `audit_id` | int | Audit Log 条目 ID（路径参数） |

#### 响应

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### 错误

- `404`：找不到条目或已确认

### POST /api/agent/audit/report

手动生成 Audit Bureau 定期报告。

#### Rate Limit

WRITE

#### 请求

```json
{
  "hours": 24
}
```

| 参数 | 类型 | 必填 | 说明 |
|-----------|------|----------|-------------|
| `hours` | int | 否 | 报告期间（小时）。默认：24，最大：720 |

#### 响应

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
