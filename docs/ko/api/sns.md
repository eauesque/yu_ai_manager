# SNS Share API

SNS 공유, Bluesky 게시, 알림 큐 관리를 위한 API입니다.

`routes/sns_share.py`에서 제공합니다. 모든 엔드포인트는 인증(PIN 세션 또는 API Key)이 필요합니다.

## 미리보기 & X Intent

### GET /api/sns/preview

게시 템플릿을 이미지 메타데이터로 확장하여 미리보기를 반환합니다. 공유 전 내용 확인에 사용합니다.

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 대상 이미지 파일 ID |
| `template` | string | 아니오 | 커스텀 템플릿 문자열 (생략 시 기본값 사용) |

### 응답

```json
{
  "text": "New artwork: sunset landscape #aiart #stablediffusion",
  "graphemes": 52,
  "meta": {
    "title": "sunset landscape",
    "model": "sd_xl_base_1.0",
    "generator": "a1111"
  }
}
```

### curl 예시

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/sns/preview?file_id=42"
```

### GET /api/sns/x/intent

X (Twitter) Web Intent URL을 생성합니다. 텍스트가 미리 입력된 X 작성 화면을 엽니다.

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 대상 이미지 파일 ID |

### 응답

```json
{
  "url": "https://twitter.com/intent/tweet?text=New+artwork%3A+sunset+landscape+%23aiart"
}
```

---

## Bluesky 게시

### POST /api/sns/bluesky/post

Bluesky에 텍스트(및 선택적으로 이미지)를 게시합니다.

### 요청

```json
{
  "file_id": 42,
  "text": "Check out my new artwork! #aiart",
  "attach_image": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file_id` | int | 예 | 대상 이미지 파일 ID |
| `text` | string | 아니오 | 게시 텍스트 (생략 시 템플릿 확장 사용) |
| `attach_image` | boolean | 아니오 | 게시물에 이미지 첨부 (기본값: false) |

### 응답

```json
{
  "ok": true,
  "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy"
}
```

### 오류 응답

```json
{
  "ok": false,
  "error": "Authentication failed: invalid app password"
}
```

### POST /api/sns/bluesky/test

설정된 인증 정보로 Bluesky 연결을 테스트합니다.

### 응답

```json
{
  "ok": true,
  "handle": "user.bsky.social",
  "display_name": "My Display Name"
}
```

### 오류 응답

```json
{
  "ok": false,
  "error": "Invalid identifier or password"
}
```

---

## SNS 설정

### GET /api/sns/config

SNS 설정을 조회합니다. 비밀번호는 마스킹되어 표시됩니다.

### 응답

```json
{
  "bluesky": {
    "handle": "user.bsky.social",
    "app_password": "****...xxxx"
  },
  "post_template": "{title} #aiart #{generator}"
}
```

### POST /api/sns/config

SNS 설정을 저장합니다.

### 요청

```json
{
  "bluesky_handle": "user.bsky.social",
  "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx",
  "post_template": "{title} #aiart #{generator}"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `bluesky_handle` | string | 아니오 | Bluesky 핸들 (예: `user.bsky.social`) |
| `bluesky_app_password` | string | 아니오 | Bluesky App Password |
| `post_template` | string | 아니오 | `{placeholder}` 변수를 포함한 기본 게시 템플릿 |

### curl 예시

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"bluesky_handle": "user.bsky.social", "bluesky_app_password": "xxxx-xxxx-xxxx-xxxx"}' \
  "http://localhost:5000/api/sns/config"
```

---

## Bluesky 알림 큐

### GET /api/sns/bsky/queue

필터를 사용하여 알림 큐 항목을 조회합니다.

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `status` | string | 필터: `pending`, `notified`, `dismissed` 또는 빈 값으로 전체 조회 |
| `type` | string | 알림 유형 필터 (예: `mention`, `reply`, `quote`, `like`, `repost`, `follow`) |
| `limit` | int | 최대 결과 수 (기본 50) |

### 응답

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "type": "mention",
        "author_handle": "someone.bsky.social",
        "author_display_name": "Someone",
        "text": "@user.bsky.social great artwork!",
        "uri": "at://did:plc:xxxxx/app.bsky.feed.post/yyyyy",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": null
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/sns/bsky/queue/pending

MCP 알림용 미처리(pending) 알림을 조회합니다.

### 응답

```json
{
  "data": {
    "items": [...],
    "count": 3,
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### POST /api/sns/bsky/queue/<queue_id>/triage

큐 항목의 트리아지 결과를 설정합니다.

### 요청

```json
{ "result": "valid" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `result` | string | 예 | `valid` 또는 `invalid` |

### PUT /api/sns/bsky/queue/<queue_id>/status

큐 항목의 상태를 업데이트합니다.

### 요청

```json
{ "status": "notified" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | 예 | `pending`, `notified` 또는 `dismissed` |

### POST /api/sns/bsky/queue/<queue_id>/respond

알림에 대해 자동 응답을 전송합니다.

### 요청

```json
{ "text": "Thank you for your kind words!" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `text` | string | 예 | 답글로 게시할 응답 텍스트 |

### POST /api/sns/bsky/queue/poll

Bluesky 새 알림을 즉시 폴링합니다.

### curl 예시

```bash
curl -X POST -H "Authorization: Bearer sk_xxxxx" \
  -H "X-Requested-With: XMLHttpRequest" \
  "http://localhost:5000/api/sns/bsky/queue/poll"
```

---

## Bluesky 모니터 설정

### GET /api/sns/bsky/monitor/config

Bluesky 알림 모니터 설정을 조회합니다.

### 응답

```json
{
  "data": {
    "poll_interval_minutes": 15,
    "auto_dismiss_follow": false,
    "auto_dismiss_like": true,
    "auto_dismiss_repost": true,
    "auto_respond_enabled": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/sns/bsky/monitor/config

Bluesky 알림 모니터 설정을 업데이트합니다. 제공된 필드만 업데이트됩니다.

### 요청

```json
{
  "poll_interval_minutes": 30,
  "auto_dismiss_follow": false,
  "auto_dismiss_like": true,
  "auto_dismiss_repost": true,
  "auto_respond_enabled": false,
  "notify_on_connect": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `poll_interval_minutes` | int | 아니오 | 폴링 간격 (분) |
| `auto_dismiss_follow` | boolean | 아니오 | 팔로우 알림 자동 해제 |
| `auto_dismiss_like` | boolean | 아니오 | 좋아요 알림 자동 해제 |
| `auto_dismiss_repost` | boolean | 아니오 | 리포스트 알림 자동 해제 |
| `auto_respond_enabled` | boolean | 아니오 | 자동 응답 활성화 |
| `notify_on_connect` | boolean | 아니오 | MCP 클라이언트 연결 시 알림 전송 |

---

## 트리아지 프롬프트 & 자동 응답 템플릿

### GET /api/sns/bsky/monitor/triage-prompts

편집 가능한 트리아지 프롬프트, 자동 응답 템플릿 및 기본값을 조회합니다.

### 응답

```json
{
  "data": {
    "triage_prompts": {
      "mention": "Evaluate this mention for relevance...",
      "reply": "Evaluate this reply...",
      "quote": "Evaluate this quote post..."
    },
    "auto_responses": {
      "mention": "Thanks for the mention!",
      "reply": "Thank you for your reply!",
      "quote": "Thanks for sharing!"
    },
    "defaults": {
      "triage_prompts": {
        "mention": "Evaluate this mention for relevance...",
        "reply": "Evaluate this reply...",
        "quote": "Evaluate this quote post..."
      },
      "auto_responses": {
        "mention": "Thanks for the mention!",
        "reply": "Thank you for your reply!",
        "quote": "Thanks for sharing!"
      }
    }
  }
}
```

### PUT /api/sns/bsky/monitor/triage-prompts

트리아지 프롬프트 및/또는 자동 응답 템플릿을 업데이트합니다. 제공된 필드만 업데이트됩니다.

### 요청

```json
{
  "triage_prompts": {
    "mention": "커스텀 멘션 트리아지 프롬프트...",
    "reply": "커스텀 답글 트리아지 프롬프트...",
    "quote": "커스텀 인용 트리아지 프롬프트..."
  },
  "auto_responses": {
    "mention": "커스텀 멘션 자동 응답...",
    "reply": "커스텀 답글 자동 응답...",
    "quote": "커스텀 인용 자동 응답..."
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `triage_prompts` | object | 아니오 | 알림 유형(`mention`, `reply`, `quote`)을 키로 한 트리아지 프롬프트 |
| `auto_responses` | object | 아니오 | 알림 유형을 키로 한 자동 응답 템플릿 |
