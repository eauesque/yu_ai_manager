# 작업 스케줄러

## 개요

작업 스케줄러는 데이터베이스 유지보수 및 외부 서비스 폴링 등의 정기 작업을 자동으로 실행합니다. APScheduler 기반의 백그라운드 스케줄러가 cron 및 interval 트리거로 작업을 관리합니다.

WebUI의 스케줄러 페이지 (`/scheduler`)에서 작업 목록 확인, 추가, 삭제, 일시 중지, 즉시 실행이 가능합니다.

## 설정

스케줄러는 기본적으로 활성화되어 있습니다. `config.json`의 `scheduler.enabled`로 제어합니다:

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

`config.json`에 정의된 작업은 서버 시작 시 자동으로 등록됩니다. WebUI에서 추가한 작업은 현재 서버 세션에서만 유효하며 재시작 시 사라집니다.

## 내장 작업 목록

### 데이터베이스 유지보수

| 작업 ID | 설명 | 권장 빈도 |
|---------|------|----------|
| `db_vacuum` | SQLite VACUUM을 실행하여 사용되지 않는 공간 회수 | 주 1회 |
| `db_integrity_check` | `PRAGMA integrity_check`로 데이터베이스 무결성 검증 | 매일 |
| `db_backup` | 데이터베이스 백업 생성 (builtin-backup 확장 기능 경유) | 매일 |

### 캐시 및 인덱스 관리

| 작업 ID | 설명 | 권장 빈도 |
|---------|------|----------|
| `thumbnail_cleanup` | 만료된 썸네일 캐시 파일 삭제 | 매일 |
| `prune_unused_tags` | 파일과 연결되지 않은 고아 태그 레코드 삭제 | 주 1회~월 1회 |
| `refresh_monthly_stats` | 월간 통계 사전 계산 캐시 갱신 | 매일 |
| `rebuild_groups_index` | 폴더/아카이브 그룹 인덱스 캐시 재구축 | 주 1회 |

### 외부 서비스 연동

| 작업 ID | 설명 | 권장 빈도 |
|---------|------|----------|
| `github_issue_poll` | GitHub API를 폴링하여 새 이슈를 로컬 큐에 추가 | 5분~1시간 |
| `bsky_notification_poll` | Bluesky API를 폴링하여 새 알림 수신 | 5분~1시간 |

## 트리거 설정

### Cron 트리거

특정 시간, 날짜에 실행합니다. Unix cron과 유사한 구문입니다.

| 파라미터 | 예시 | 설명 |
|---------|------|------|
| `hour` | `3`, `*/6`, `1,13` | 시 (0-23). `*`는 매시 |
| `minute` | `0`, `30`, `0,30` | 분 (0-59). `*`는 매분 |
| `day` | `1`, `15`, `1,15` | 일 (1-31). `*`는 매일 |
| `day_of_week` | `sun`, `mon-fri`, `0-4` | 요일. `*`는 매일 |

**예시**: 매월 1일과 15일 오전 2시 30분에 실행

```json
{ "trigger": "cron", "day": "1,15", "hour": 2, "minute": 30 }
```

### Interval 트리거

일정 간격으로 반복 실행합니다.

| 파라미터 | 예시 | 설명 |
|---------|------|------|
| `hours` | `2` | 시간 간격 |
| `minutes` | `30` | 분 간격 |

**예시**: 30분마다 실행

```json
{ "trigger": "interval", "minutes": 30 }
```

## WebUI 사용법

### 작업 목록

스케줄러 페이지에 등록된 모든 작업이 표시됩니다. 각 작업의 상태(활성/일시 중지), 트리거 설정, 다음 실행 시간을 확인할 수 있습니다.

### 작업 추가

1. **작업 추가** 버튼 클릭
2. 고유한 작업 ID 입력
3. 드롭다운에서 함수 선택
4. 트리거 유형 선택 (cron / interval)
5. 스케줄 파라미터 설정 (`*`로 와일드카드 지정 가능)
6. **추가** 클릭

### 작업 조작

- **지금 실행**: 스케줄 외에 즉시 1회 실행
- **일시 중지 / 재개**: 정기 실행을 임시로 중지하거나 재개
- **삭제**: 작업을 완전히 제거 (config.json의 작업은 다음 시작 시 복원됨)

### 실행 기록

페이지 하단에 최근 실행 기록(최대 50건)이 표시됩니다. 성공/실패 상태와 결과 메시지를 확인할 수 있습니다. 작업 완료 시 SSE로 실시간 업데이트됩니다.

## MCP 도구

MCP 클라이언트(예: Claude Desktop)에서 스케줄러를 관리할 수 있습니다:

| 도구 | 설명 |
|------|------|
| `get_scheduler_status` | 스케줄러 실행 상태 조회 |
| `list_scheduled_jobs` | 등록된 작업 목록 조회 |
| `trigger_scheduled_job` | 작업 즉시 실행 트리거 |
| `pause_scheduled_job` | 작업 일시 중지 |
| `resume_scheduled_job` | 작업 재개 |
| `get_scheduler_history` | 실행 기록 조회 |

## 팁

- **폴링 작업**(`github_issue_poll`, `bsky_notification_poll`)은 interval 트리거가 적합합니다. cron으로 고정 시간에 설정하면 폴링 간격이 너무 길어질 수 있습니다
- **`db_vacuum`**은 쓰기 잠금을 획득하므로 트래픽이 적은 시간대(예: 심야)에 설정하는 것을 권장합니다
- **`db_backup`**은 builtin-backup 확장의 쿨다운 설정을 따릅니다. 짧은 interval로 설정해도 쿨다운 기간에는 백업이 건너뛰어집니다
- **실행 기록은 메모리에 저장**됩니다(최대 100건). 서버 재시작 시 기록이 초기화됩니다
