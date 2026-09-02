# GitHub Integration API

GitHub 계정 관리, Issues, Pull Requests, 알림 및 Releases를 위한 API입니다.

`builtin-github` 확장에서 제공합니다. 모든 엔드포인트는 인증(PIN 세션 또는 API Key)이 필요합니다.

## 계정 관리

### GET /api/github/accounts

등록된 GitHub 계정 목록을 조회합니다. 응답에서 토큰은 마스킹되어 표시됩니다.

### 응답

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

새 GitHub 계정을 등록합니다.

### 요청

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `label` | string | 예 | 고유한 계정 식별 라벨 |
| `token` | string | 예 | GitHub Personal Access Token |
| `repos` | string[] | 예 | 모니터링할 저장소 (`owner/repo` 형식) |

### 응답

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

기존 계정의 설정을 업데이트합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |

### 요청

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `token` | string | 아니오 | 새 토큰 값 |
| `repos` | string[] | 아니오 | 업데이트된 저장소 목록 |
| `enabled` | boolean | 아니오 | 계정 활성화 또는 비활성화 |

### DELETE /api/github/accounts/<label>

계정을 제거합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |

---

## Issues

### GET /api/github/issues/<label>

계정의 저장소에서 Issues를 가져옵니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |
| `state` | string | Issue 상태 필터 (`open`, `closed`, `all`) |
| `labels` | string | 라벨 필터 (쉼표로 구분) |
| `since` | string | 이 날짜 이후에 업데이트된 Issues만 조회 (ISO 8601) |
| `repo` | string | 특정 저장소로 필터링 |

### curl 예시

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

새 Issue를 생성합니다.

### 요청

```json
{
  "repo": "owner/repo1",
  "title": "Bug: 로그인 화면 크래시",
  "body": "재현 단계:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `repo` | string | 예 | 대상 저장소 (`owner/repo`) |
| `title` | string | 예 | Issue 제목 |
| `body` | string | 아니오 | Issue 본문 (Markdown) |
| `labels` | string[] | 아니오 | 적용할 라벨 |

### GET /api/github/issue/<label>/<repo>/<number>

댓글을 포함한 Issue 상세 정보를 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 |
| `repo` | string | 저장소 이름 (`owner/repo`) |
| `number` | int | Issue 번호 |

### POST /api/github/triage/<label>

Issue 트리아지(분류 및 우선순위 지정)를 실행합니다.

### 요청

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `state` | string | 아니오 | 대상 Issues의 상태 필터 |
| `since` | string | 아니오 | 이 날짜 이후에 업데이트된 Issues만 트리아지 (ISO 8601) |

---

## Pull Requests

### GET /api/github/pulls/<label>

Pull Requests 목록을 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |
| `state` | string | PR 상태 (`open`, `closed`, `all`) |
| `repo` | string | 특정 저장소로 필터링 |

### GET /api/github/pull/<label>/<repo>/<number>

변경된 파일을 포함한 PR 상세 정보를 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 |
| `repo` | string | 저장소 이름 (`owner/repo`) |
| `number` | int | PR 번호 |

---

## 알림

### GET /api/github/notifications/<label>

알림 목록을 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |
| `all` | string | `true`로 설정하면 읽은 알림도 포함 (기본값: 미읽은 알림만) |

### PATCH /api/github/notifications/<label>/<thread_id>

특정 알림 스레드를 읽음으로 표시합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 |
| `thread_id` | string | 알림 스레드 ID |

### POST /api/github/notifications/<label>/mark-all-read

모든 알림을 읽음으로 표시합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |

---

## Discussions

### GET /api/github/discussions/<label>

GitHub Discussions를 가져옵니다 (GraphQL API 사용).

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |
| `repo` | string | 특정 저장소로 필터링 (`owner/repo`) |

---

## Releases

### GET /api/github/releases/<label>

Releases 목록을 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |
| `repo` | string | 특정 저장소로 필터링 (`owner/repo`) |

---

## 저장소 통계

### GET /api/github/repo-stats/<label>/<repo>

단일 저장소의 통계를 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 |
| `repo` | string | 저장소 이름 (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

등록된 모든 저장소의 통계를 한 번에 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |

---

## 속도 제한

### GET /api/github/rate-limit/<label>

GitHub API 속도 제한 상태를 확인합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `label` | string | 계정 라벨 (경로 매개변수) |

### 응답 예시

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

## 트리아지 프롬프트

### GET /api/github/triage-prompts

Issue/PR/Discussion용 편집 가능한 트리아지 프롬프트와 기본값을 조회합니다.

### 응답

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

트리아지 프롬프트를 업데이트합니다. 제공된 필드만 업데이트됩니다.

### 요청

```json
{
  "issue": "커스텀 Issue 트리아지 프롬프트...",
  "pr": "커스텀 PR 프롬프트...",
  "discussion": "커스텀 Discussion 프롬프트..."
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `issue` | string | 아니오 | Issue용 트리아지 프롬프트 |
| `pr` | string | 아니오 | Pull Request용 트리아지 프롬프트 |
| `discussion` | string | 아니오 | Discussion용 트리아지 프롬프트 |

---

## Issue 큐

### GET /api/github/queue

상태 필터를 사용하여 Issue 큐 항목을 조회합니다.

### 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `status` | string | 필터: `pending`, `notified`, `dismissed` 또는 빈 값으로 전체 조회 |
| `limit` | int | 최대 결과 수 (기본 50, 최대 200) |

### 응답

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "버그 리포트 제목",
        "body": "Issue 본문...",
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

MCP 알림용 미확인(pending) Issue를 조회합니다.

### 응답

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

큐 항목의 트리아지 결과를 설정합니다.

### 요청

```json
{ "result": "valid" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `result` | string | 예 | `valid` 또는 `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

큐 항목을 해제합니다. 선택적으로 GitHub에서 Issue를 자동으로 닫을 수 있습니다.

### 요청

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `auto_close` | boolean | 아니오 | GitHub에서 템플릿 댓글과 함께 Issue를 닫기 |
| `account_label` | string | 아니오 | `auto_close`가 true인 경우 필수 |

### PUT /api/github/queue/<queue_id>/status

큐 항목의 상태를 업데이트합니다.

### 요청

```json
{ "status": "notified" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | 예 | `pending`, `notified` 또는 `dismissed` |

### GET /api/github/queue/config

Issue 큐 설정을 조회합니다.

### 응답

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

Issue 큐 설정을 업데이트합니다.

### 요청

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

모든 계정의 새 Issue를 즉시 폴링합니다.

---

## WebUI

### GET /ext/github

GitHub Integration WebUI 페이지입니다. 브라우저에서 직접 접근할 수 있습니다. 인증된 PIN 세션이 필요합니다.
