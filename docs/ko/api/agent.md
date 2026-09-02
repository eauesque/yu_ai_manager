# Agent Safety Gateway API

AI 에이전트 안전 제어를 관리하는 API입니다. Kill Switch, Circuit Breaker, Budget, Action Journal, Approval Gate, Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly Detection 및 Audit Bureau 기능을 제공합니다.

모든 POST/DELETE 엔드포인트는 `X-Requested-With` 헤더가 필요합니다 (Bearer API Key 사용 시 제외).

---

## Kill Switch

### POST /api/agent/kill

Kill Switch를 활성화하여 모든 에이전트 작업을 즉시 중단합니다.

#### Rate Limit

WRITE

#### 요청

```json
{
  "reason": "Manual kill via API"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `reason` | string | 아니오 | 중단 사유. 기본값: `"Manual kill via API"` |

#### 응답

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

Kill Switch를 해제하여 에이전트 작업을 재개합니다.

#### Rate Limit

WRITE

#### 요청

없음 (빈 본문)

#### 응답

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

Kill Switch, Circuit Breaker, Budget의 통합 상태를 가져옵니다.

#### 파라미터

없음

#### 응답

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

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `kill_switch` | object | Kill Switch 상세 상태 |
| `circuit_breaker` | object | Circuit Breaker 상세 상태. 에러 시 `{"enabled": false, "state": "unknown"}` 반환 |
| `budget` | object | Budget 상세 상태. 에러 시 빈 객체 반환 |
| `killed` | boolean | Kill Switch 활성화 플래그 (최상위, 하위 호환성) |
| `reason` | string | Kill Switch 사유 (하위 호환성) |
| `killed_at` | string | Kill Switch 활성화 시간 (하위 호환성) |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Circuit Breaker 상태를 가져옵니다.

#### 파라미터

없음

#### 응답

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `enabled` | boolean | Circuit Breaker 활성화 여부 |
| `state` | string | 상태: `"closed"` (정상), `"open"` (트리거됨), `"half_open"` (탐색 중) |
| `failure_count` | int | 연속 실패 횟수 |
| `threshold` | int | open으로 전환되는 실패 횟수 임계값 |

### POST /api/agent/circuit-breaker/reset

Circuit Breaker를 closed 상태로 초기화합니다.

#### Rate Limit

WRITE

#### 요청

없음 (빈 본문)

#### 응답

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

현재 세션의 잔여 예산을 가져옵니다.

#### 파라미터

없음

#### 응답

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `session_id` | string | 세션 ID |
| `used` | int | 소비된 작업 수 |
| `limit` | int | 허용된 최대 작업 수 |
| `remaining` | int | 잔여 작업 수 |

### POST /api/agent/budget/reset

예산 카운터를 초기화합니다.

#### Rate Limit

WRITE

#### 요청

없음 (빈 본문)

#### 응답

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

Action Journal을 검색합니다. 에이전트가 실행한 작업 이력을 반환합니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `tool_name` | string | 아니오 | 도구 이름으로 필터링 |
| `status` | string | 아니오 | 상태로 필터링 |
| `session_id` | string | 아니오 | 세션 ID로 필터링 |
| `limit` | int | 아니오 | 최대 결과 수 (기본값: 50, 최대: 200) |
| `offset` | int | 아니오 | 오프셋 (기본값: 0) |

#### 응답

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

Action Journal 통계를 가져옵니다.

#### 파라미터

없음

#### 응답

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

대기 중인 승인 요청 목록을 가져옵니다.

#### 파라미터

없음

#### 응답

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

승인 요청에 응답합니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `request_id` | string | 요청 ID (경로 파라미터) |

#### 요청

```json
{
  "decision": "allow"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `decision` | string | 예 | `"allow"` (허용), `"deny"` (거부), `"always_allow"` (항상 허용) |

#### 응답

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### 에러

- `400`: `decision`이 `allow`/`deny`/`always_allow` 중 하나가 아님
- `404`: 요청을 찾을 수 없거나 이미 응답됨

### GET /api/agent/approval/history

승인 이력을 가져옵니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `limit` | int | 아니오 | 최대 결과 수 (기본값: 50, 최대: 200) |

#### 응답

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

모든 세션의 Scope Fence 상태를 가져옵니다.

#### 파라미터

없음

#### 응답

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

특정 세션의 scope를 가져옵니다.

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `session_id` | string | 세션 ID (경로 파라미터) |

#### 응답

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### 에러

- `404`: 세션 scope를 찾을 수 없음

### POST /api/agent/scope/\<session_id\>

세션 scope를 설정합니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `session_id` | string | 세션 ID (경로 파라미터) |

#### 요청

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `preset` | string | 아니오 | 프리셋 이름: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | 아니오 | 거부할 도구 이름 목록 |
| `name` | string | 아니오 | scope의 표시 이름 |
| `duration_hours` | number | 아니오 | scope 만료 시간 (시간) |

#### 응답

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

#### 에러

- `400`: `denied`가 목록이 아님

### DELETE /api/agent/scope/\<session_id\>

세션 scope를 삭제합니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `session_id` | string | 세션 ID (경로 파라미터) |

#### 응답

```json
{
  "ok": true
}
```

---

## Auto-Approve 규칙

### GET /api/agent/auto-approve

Auto-Approve 규칙 목록을 가져옵니다.

#### 파라미터

없음

#### 응답

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

Auto-Approve 규칙을 추가합니다.

#### Rate Limit

WRITE

#### 요청

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `tool` | string | 예 | 대상 도구 이름 |
| `conditions` | object | 아니오 | 자동 승인 조건. 생략 시 무조건 승인 |

#### 응답

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

#### 에러

- `400`: `tool`이 지정되지 않음
- `400`: `conditions`가 딕셔너리가 아님

### DELETE /api/agent/auto-approve/\<index\>

Auto-Approve 규칙을 삭제합니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `index` | int | 규칙 인덱스 (경로 파라미터) |

#### 응답

```json
{
  "ok": true
}
```

#### 에러

- `404`: 규칙을 찾을 수 없음

---

## Tool Classification

### GET /api/agent/tool-levels

도구 분류 정보를 가져옵니다. `tool` 파라미터 지정 시 해당 도구의 등급만 반환하고, 그렇지 않으면 모든 도구의 요약과 커스텀 오버라이드를 반환합니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `tool` | string | 아니오 | 도구 이름. 지정 시 해당 도구의 등급만 반환 |

#### 응답 (특정 도구)

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### 응답 (모든 도구)

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

기록된 작업을 되돌립니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `journal_id` | int | Journal 항목 ID (경로 파라미터) |

#### 응답

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### 에러

- `400`: 되돌리기 실패 (되돌릴 수 없는 작업, 이미 되돌려진 작업 등)

### GET /api/agent/undoable

되돌릴 수 있는 작업 목록을 가져옵니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `session_id` | string | 아니오 | 세션 ID로 필터링 |
| `limit` | int | 아니오 | 최대 결과 수 (기본값: 50, 최대: 200) |

#### 응답

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

Anomaly Detection 상태를 가져옵니다.

#### 파라미터

없음

#### 응답

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

Anomaly Detection 경고를 가져옵니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `limit` | int | 아니오 | 최대 결과 수 (기본값: 50, 최대: 200) |

#### 응답

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

Anomaly Detection 이력 및 경고를 초기화합니다.

#### Rate Limit

WRITE

#### 요청

없음 (빈 본문)

#### 응답

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Audit Bureau 상태를 가져옵니다.

#### 파라미터

없음

#### 응답

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

Audit Log를 검색합니다.

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `event_type` | string | 아니오 | 이벤트 유형으로 필터링 |
| `severity` | string | 아니오 | 심각도로 필터링 |
| `source` | string | 아니오 | 출처로 필터링 |
| `unacknowledged` | string | 아니오 | `"1"` 또는 `"true"`로 설정하면 미확인 항목만 반환 |
| `limit` | int | 아니오 | 최대 결과 수 (기본값: 50, 최대: 200) |
| `offset` | int | 아니오 | 오프셋 (기본값: 0) |

#### 응답

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

Audit Log 항목을 사용자가 확인한 것으로 표시합니다.

#### Rate Limit

WRITE

#### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `audit_id` | int | Audit Log 항목 ID (경로 파라미터) |

#### 응답

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### 에러

- `404`: 항목을 찾을 수 없거나 이미 확인됨

### POST /api/agent/audit/report

Audit Bureau 정기 보고서를 수동으로 생성합니다.

#### Rate Limit

WRITE

#### 요청

```json
{
  "hours": 24
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `hours` | int | 아니오 | 보고 기간 (시간). 기본값: 24, 최대: 720 |

#### 응답

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
