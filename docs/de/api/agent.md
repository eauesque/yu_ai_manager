# Agent Safety Gateway API

APIs für die Verwaltung von AI-Agent-Sicherheitskontrollen.

All POST/DELETE endpoints require the `X-Requested-With` header (except when using Bearer API Key).

---

## Kill Switch

### POST /api/agent/kill

Activate the Kill Switch to immediately halt all agent operations.

#### Rate Limit

WRITE

#### Request

```json
{
  "reason": "Manual kill via API"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reason` | string | No | Reason for stopping. Defaults to `"Manual kill via API"` |

#### Response

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

Deactivate the Kill Switch to resume agent operations.

#### Rate Limit

WRITE

#### Request

None (empty body)

#### Response

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

Get unified status of Kill Switch, Circuit Breaker, and Budget.

#### Parameters

None

#### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `kill_switch` | object | Detailed Kill Switch status |
| `circuit_breaker` | object | Detailed Circuit Breaker status. Returns `{"enabled": false, "state": "unknown"}` on error |
| `budget` | object | Detailed Budget status. Returns empty object on error |
| `killed` | boolean | Kill Switch active flag (top-level for backward compatibility) |
| `reason` | string | Kill Switch reason (backward compatibility) |
| `killed_at` | string | Kill Switch activation time (backward compatibility) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Get Circuit Breaker state.

#### Parameters

None

#### Response

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Whether Circuit Breaker is enabled |
| `state` | string | State: `"closed"` (normal), `"open"` (tripped), `"half_open"` (probing) |
| `failure_count` | int | Consecutive failure count |
| `threshold` | int | Failure count threshold to trip open |

### POST /api/agent/circuit-breaker/reset

Reset Circuit Breaker to closed state.

#### Rate Limit

WRITE

#### Request

None (empty body)

#### Response

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

Get budget remaining for the current session.

#### Parameters

None

#### Response

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session ID |
| `used` | int | Number of actions consumed |
| `limit` | int | Maximum allowed actions |
| `remaining` | int | Actions remaining |

### POST /api/agent/budget/reset

Reset the budget counter.

#### Rate Limit

WRITE

#### Request

None (empty body)

#### Response

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

Search the Action Journal. Returns history of actions executed by agents.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool_name` | string | No | Filter by tool name |
| `status` | string | No | Filter by status |
| `session_id` | string | No | Filter by session ID |
| `limit` | int | No | Max results (default: 50, max: 200) |
| `offset` | int | No | Offset (default: 0) |

#### Response

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

Get Action Journal statistics.

#### Parameters

None

#### Response

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

Get list of pending approval requests.

#### Parameters

None

#### Response

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

Respond to an approval request.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `request_id` | string | Request ID (path parameter) |

#### Request

```json
{
  "decision": "allow"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `decision` | string | Yes | `"allow"` (permit), `"deny"` (reject), `"always_allow"` (always permit) |

#### Response

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Errors

- `400`: `decision` is not one of `allow`/`deny`/`always_allow`
- `404`: Request not found or already responded

### GET /api/agent/approval/history

Get approval history.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Response

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

Get Scope Fence state for all sessions.

#### Parameters

None

#### Response

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

Get scope for a specific session.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Response

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Errors

- `404`: Session scope not found

### POST /api/agent/scope/\<session_id\>

Set session scope.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Request

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `preset` | string | No | Preset name: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | No | List of denied tool names |
| `name` | string | No | Display name for the scope |
| `duration_hours` | number | No | Scope expiration in hours |

#### Response

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

#### Errors

- `400`: `denied` is not a list

### DELETE /api/agent/scope/\<session_id\>

Delete a session scope.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Response

```json
{
  "ok": true
}
```

---

## Auto-Approve Rules

### GET /api/agent/auto-approve

Get list of auto-approve rules.

#### Parameters

None

#### Response

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

Add an auto-approve rule.

#### Rate Limit

WRITE

#### Request

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool` | string | Yes | Target tool name |
| `conditions` | object | No | Conditions for auto-approval. Omit for unconditional approval |

#### Response

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

#### Errors

- `400`: `tool` is not specified
- `400`: `conditions` is not a dict

### DELETE /api/agent/auto-approve/\<index\>

Delete an auto-approve rule.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `index` | int | Rule index (path parameter) |

#### Response

```json
{
  "ok": true
}
```

#### Errors

- `404`: Rule not found

---

## Tool Classification

### GET /api/agent/tool-levels

Get tool classification information. When `tool` parameter is specified, returns the level for that specific tool. Otherwise returns a summary of all tools and any overrides.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool` | string | No | Tool name. If specified, returns only that tool's level |

#### Response (specific tool)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Response (all tools)

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

Undo a journaled action.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `journal_id` | int | Journal entry ID (path parameter) |

#### Response

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Errors

- `400`: Undo failed (action not undoable, already undone, etc.)

### GET /api/agent/undoable

Get list of undoable actions.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | No | Filter by session ID |
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Response

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

Get Anomaly Detection state.

#### Parameters

None

#### Response

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

Get Anomaly Detection alerts.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Response

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

Reset Anomaly Detection history and alerts.

#### Rate Limit

WRITE

#### Request

None (empty body)

#### Response

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Get Audit Bureau state.

#### Parameters

None

#### Response

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

Search the Audit Log.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `event_type` | string | No | Filter by event type |
| `severity` | string | No | Filter by severity |
| `source` | string | No | Filter by source |
| `unacknowledged` | string | No | Set to `"1"` or `"true"` to return only unacknowledged entries |
| `limit` | int | No | Max results (default: 50, max: 200) |
| `offset` | int | No | Offset (default: 0) |

#### Response

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

Mark an audit log entry as user-acknowledged.

#### Rate Limit

WRITE

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `audit_id` | int | Audit log entry ID (path parameter) |

#### Response

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Errors

- `404`: Entry not found or already acknowledged

### POST /api/agent/audit/report

Manually generate an Audit Bureau periodic report.

#### Rate Limit

WRITE

#### Request

```json
{
  "hours": 24
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `hours` | int | No | Report period in hours. Default: 24, max: 720 |

#### Response

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
