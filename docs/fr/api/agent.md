# API Agent - Passerelle de sécurité

APIs pour la gestion des contrôles de sécurité des agents IA. Provides Kill Switch, Circuit Breaker, Budget, Action Journal, Approval Gate, Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly Detection, and Audit Bureau functionality.

All POST/DELETE endpoints require the `X-Requêteed-With` header (except lors de l'utilisation d'une clé API Bearer).

---

## Bouton d'arrêt

### POST /api/agent/kill

Activate the Kill Switch to immediately halt all agent operations.

#### Rate Limit

WRITE

#### Requête

```json
{
  "reason": "Manual kill via API"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `reason` | string | No | Reason for stopping. Défauts to `"Manual kill via API"` |

#### Réponse

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

#### Requête

None (empty body)

#### Réponse

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

#### Paramètres

None

#### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `kill_switch` | object | Detailed Kill Switch status |
| `circuit_breaker` | object | Detailed Circuit Breaker status. Returns `{"enabled": false, "state": "unknown"}` on error |
| `budget` | object | Detailed Budget status. Returns empty object on error |
| `killed` | boolean | Kill Switch active flag (top-level for backward compatibility) |
| `reason` | string | Kill Switch reason (backward compatibility) |
| `killed_at` | string | Kill Switch activation time (backward compatibility) |

---

## Disjoncteur

### GET /api/agent/circuit-breaker

Get Circuit Breaker state.

#### Paramètres

None

#### Réponse

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `enabled` | boolean | Si Circuit Breaker is enabled |
| `state` | string | State: `"closed"` (normal), `"open"` (tripped), `"half_open"` (probing) |
| `failure_count` | int | Consecutive failure count |
| `threshold` | int | Failure count threshold to trip open |

### POST /api/agent/circuit-breaker/reset

Reset Circuit Breaker to closed state.

#### Rate Limit

WRITE

#### Requête

None (empty body)

#### Réponse

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

#### Paramètres

None

#### Réponse

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session ID |
| `used` | int | Number of actions consumed |
| `limit` | int | Maximum allowed actions |
| `remaining` | int | Actions remaining |

### POST /api/agent/budget/reset

Reset the budget counter.

#### Rate Limit

WRITE

#### Requête

None (empty body)

#### Réponse

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

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `tool_name` | string | No | Filter by tool name |
| `status` | string | No | Filter by status |
| `session_id` | string | No | Filter by session ID |
| `limit` | int | No | Max results (default: 50, max: 200) |
| `offset` | int | No | Offset (default: 0) |

#### Réponse

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

#### Paramètres

None

#### Réponse

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

#### Paramètres

None

#### Réponse

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

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `request_id` | string | Requête ID (path parameter) |

#### Requête

```json
{
  "decision": "allow"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `decision` | string | Yes | `"allow"` (permit), `"deny"` (reject), `"always_allow"` (always permit) |

#### Réponse

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### Erreurs

- `400`: `decision` is not one of `allow`/`deny`/`always_allow`
- `404`: Requête not found or already responded

### GET /api/agent/approval/history

Get approval history.

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Réponse

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

#### Paramètres

None

#### Réponse

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

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Réponse

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### Erreurs

- `404`: Session scope not found

### POST /api/agent/scope/\<session_id\>

Set session scope.

#### Rate Limit

WRITE

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Requête

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `preset` | string | No | Preset name: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | No | List of denied tool names |
| `name` | string | No | Display name for the scope |
| `duration_hours` | number | No | Scope expiration in hours |

#### Réponse

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

#### Erreurs

- `400`: `denied` is not a list

### DELETE /api/agent/scope/\<session_id\>

Delete a session scope.

#### Rate Limit

WRITE

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID (path parameter) |

#### Réponse

```json
{
  "ok": true
}
```

---

## Auto-Approve Rules

### GET /api/agent/auto-approve

Get list of auto-approve rules.

#### Paramètres

None

#### Réponse

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

#### Requête

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `tool` | string | Yes | Target tool name |
| `conditions` | object | No | Conditions for auto-approval. Omit for unconditional approval |

#### Réponse

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

#### Erreurs

- `400`: `tool` is not specified
- `400`: `conditions` is not a dict

### DELETE /api/agent/auto-approve/\<index\>

Delete an auto-approve rule.

#### Rate Limit

WRITE

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `index` | int | Rule index (path parameter) |

#### Réponse

```json
{
  "ok": true
}
```

#### Erreurs

- `404`: Rule not found

---

## Tool Classification

### GET /api/agent/tool-levels

Get tool classification information. When `tool` parameter is specified, returns the level for that specific tool. Otherwise returns a summary of all tools and any overrides.

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `tool` | string | No | Tool name. If specified, returns only that tool's level |

#### Réponse (specific tool)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### Réponse (all tools)

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

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `journal_id` | int | Journal entry ID (path parameter) |

#### Réponse

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### Erreurs

- `400`: Undo failed (action not undoable, already undone, etc.)

### GET /api/agent/undoable

Get list of undoable actions.

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `session_id` | string | No | Filter by session ID |
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Réponse

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

#### Paramètres

None

#### Réponse

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

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `limit` | int | No | Max results (default: 50, max: 200) |

#### Réponse

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

#### Requête

None (empty body)

#### Réponse

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Get Audit Bureau state.

#### Paramètres

None

#### Réponse

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

#### Paramètres

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `event_type` | string | No | Filter by event type |
| `severity` | string | No | Filter by severity |
| `source` | string | No | Filter by source |
| `unacknowledged` | string | No | Set to `"1"` or `"true"` to return only unacknowledged entries |
| `limit` | int | No | Max results (default: 50, max: 200) |
| `offset` | int | No | Offset (default: 0) |

#### Réponse

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

#### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `audit_id` | int | Audit log entry ID (path parameter) |

#### Réponse

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### Erreurs

- `404`: Entry not found or already acknowledged

### POST /api/agent/audit/report

Manually generate an Audit Bureau periodic report.

#### Rate Limit

WRITE

#### Requête

```json
{
  "hours": 24
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `hours` | int | No | Report period in hours. Défaut: 24, max: 720 |

#### Réponse

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
