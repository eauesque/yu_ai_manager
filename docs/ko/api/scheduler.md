# Scheduler API

작업 스케줄러 관리 API. 상태 조회, 작업 추가/삭제, 일시정지/재개, 즉시 실행 트리거, 실행 이력 조회가 가능합니다.

## 설정

`config.json`에서 스케줄러를 활성화하고 내장 작업의 스케줄을 설정합니다:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

### 내장 작업

| 작업 ID | 설명 | 기본 스케줄 |
|---------|------|-----------|
| `db_vacuum` | 데이터베이스 VACUUM (공간 회수) | 매주 일요일 03:00 |
| `db_integrity_check` | 데이터베이스 무결성 검사 | 매일 04:00 |
| `thumbnail_cleanup` | 썸네일 캐시 정리 | 매일 05:00 |
| `github_issue_poll` | GitHub 이슈 폴링 | 미설정 (WebUI에서 추가) |
| `bsky_notification_poll` | Bluesky 알림 폴링 | 미설정 (WebUI에서 추가) |
| `prune_unused_tags` | 미사용 태그 정리 | 미설정 (WebUI에서 추가) |
| `refresh_monthly_stats` | 월간 통계 캐시 갱신 | 미설정 (WebUI에서 추가) |
| `rebuild_groups_index` | 그룹 인덱스 재구축 | 미설정 (WebUI에서 추가) |
| `db_backup` | 데이터베이스 백업 | 미설정 (WebUI에서 추가) |

## GET /api/scheduler/status

스케줄러 상태와 모든 작업 정보를 반환합니다.

### 응답

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | boolean | 성공 플래그 |
| `data.running` | boolean | 스케줄러 실행 중 여부 |
| `data.jobs` | array | 작업 목록 (다음 실행 시간 포함) |

### 예제

```bash
curl "http://localhost:5100/api/scheduler/status"
```

```json
{
  "ok": true,
  "data": {
    "running": true,
    "jobs": [
      {
        "job_id": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      },
      {
        "job_id": "db_integrity_check",
        "trigger": "cron",
        "next_run": "2026-03-16T04:00:00",
        "paused": false
      }
    ]
  }
}
```

## GET /api/scheduler/jobs

`next_run` 시간이 포함된 작업 목록을 반환합니다.

### 응답

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | boolean | 성공 플래그 |
| `data.jobs` | array | 작업 객체 배열 |
| `data.jobs[].job_id` | string | 작업 ID |
| `data.jobs[].func_name` | string | 실행 함수명 |
| `data.jobs[].trigger` | string | 트리거 유형 (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | 다음 예정 실행 시간 (ISO 8601) |
| `data.jobs[].paused` | boolean | 일시정지 여부 |

### 예제

```bash
curl "http://localhost:5100/api/scheduler/jobs"
```

```json
{
  "ok": true,
  "data": {
    "jobs": [
      {
        "job_id": "db_vacuum",
        "func_name": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      }
    ]
  }
}
```

## POST /api/scheduler/jobs

커스텀 작업을 추가합니다.

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `job_id` | string | Yes | 고유한 작업 ID |
| `func_name` | string | Yes | 실행할 함수명 |
| `trigger` | string | Yes | 트리거 유형 (`cron`, `interval`, `date`) |
| `trigger_args` | object | Yes | 트리거 인수 (`hour`, `minute`, `day_of_week` 등) |

### 예제

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "custom_cleanup",
       "func_name": "thumbnail_cleanup",
       "trigger": "cron",
       "trigger_args": { "hour": 6, "minute": 30 }
     }'
```

```json
{
  "ok": true,
  "data": {
    "job_id": "custom_cleanup",
    "next_run": "2026-03-16T06:30:00"
  }
}
```

## DELETE /api/scheduler/jobs/\<id\>

지정한 작업을 삭제합니다. **DESTRUCTIVE** 티어 속도 제한이 적용됩니다.

### 경로 매개변수

| 매개변수 | 타입 | 설명 |
|---------|------|------|
| `id` | string | 작업 ID |

### 예제

```bash
curl -X DELETE "http://localhost:5100/api/scheduler/jobs/custom_cleanup" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "removed": "custom_cleanup" }
}
```

## POST /api/scheduler/jobs/\<id\>/pause

작업을 일시정지합니다.

### 예제

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/pause" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": true }
}
```

## POST /api/scheduler/jobs/\<id\>/resume

일시정지된 작업을 재개합니다.

### 예제

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/resume" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": false }
}
```

## POST /api/scheduler/jobs/\<id\>/trigger

작업을 즉시 실행합니다. **WRITE** 티어 속도 제한이 적용됩니다.

### 예제

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/trigger" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "triggered": true }
}
```

## GET /api/scheduler/history

실행 이력을 최신순으로 반환합니다 (최대 100건).

### 응답

| 필드 | 타입 | 설명 |
|------|------|------|
| `ok` | boolean | 성공 플래그 |
| `data.history` | array | 실행 이력 배열 |
| `data.history[].job_id` | string | 작업 ID |
| `data.history[].executed_at` | string | 실행 시각 (ISO 8601) |
| `data.history[].status` | string | 결과 (`success`, `error`) |
| `data.history[].duration_ms` | number | 실행 시간 (밀리초) |
| `data.history[].error` | string\|null | 오류 메시지 (실패 시에만) |

### 예제

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_integrity_check",
        "executed_at": "2026-03-15T04:00:02",
        "status": "success",
        "duration_ms": 1234,
        "error": null
      },
      {
        "job_id": "thumbnail_cleanup",
        "executed_at": "2026-03-15T05:00:01",
        "status": "success",
        "duration_ms": 567,
        "error": null
      }
    ]
  }
}
```

## SSE 이벤트

스케줄러 관련 이벤트는 SSE 공유 엔진을 통해 전달됩니다.

| 이벤트 | 데이터 | 설명 |
|--------|--------|------|
| `scheduler.job_executed` | `{ job_id, result }` | 작업 실행 완료 |
| `scheduler.job_error` | `{ job_id, error }` | 작업 실행 오류 |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP 도구

| 도구명 | 설명 |
|--------|------|
| `get_scheduler_status` | 스케줄러 실행 상태 조회 |
| `list_scheduled_jobs` | 등록된 작업 목록 조회 |
| `trigger_scheduled_job` | 작업 즉시 실행 |
| `pause_scheduled_job` | 작업 일시정지 |
| `resume_scheduled_job` | 작업 재개 |
| `get_scheduler_history` | 실행 이력 조회 |

## 속도 제한

| 엔드포인트 | 메서드 | 티어 |
|-----------|--------|------|
| `/api/scheduler/status` | GET | READ (무제한) |
| `/api/scheduler/jobs` | GET | READ (무제한) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (무제한) |
