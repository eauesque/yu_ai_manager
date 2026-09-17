# Inbound Webhook API

외부 서비스에서 yu_ai_manager의 event_bus로 이벤트를 전송하기 위한 수신 엔드포인트.

## 수신 엔드포인트（인증 불필요 — token 기반）

`POST /api/webhooks/receive/{token}`

### 요청 본문

| 필드 | 타입 | 설명 |
|------|------|------|
| event | string | 발생시킬 event_type（생략 시: `webhook.received`） |
| data | object | 이벤트 데이터 |

### 응답

```json
{"ok": true, "event": "scan.start"}
```

### 오류

| 코드 | 설명 |
|------|------|
| 403 | token 유효하지 않음 / HMAC 불일치 / event가 allowed_events 외 |

## 관리 API（PIN 세션 필요）

### 생성

`POST /api/webhooks/inbound`

```json
{"label": "n8n trigger", "allowed_events": ["scan.start"]}
```

응답:

```json
{
  "id": "iwh_a1b2c3...",
  "token": "64char_hex...",
  "label": "n8n trigger",
  "allowed_events": ["scan.start"],
  "active": true,
  "created_at": 1712188800
}
```

### 목록

`GET /api/webhooks/inbound`

### 업데이트

`PUT /api/webhooks/inbound/{id}`

```json
{"label": "updated", "allowed_events": ["scan.start", "tag.add"], "active": true}
```

### 삭제

`DELETE /api/webhooks/inbound/{id}`

## 인증

- URL 내 token이 일치하면 수락
- `X-Webhook-Signature` 헤더가 있으면 HMAC-SHA256으로 추가 검증（선택 사항）

## 보안

- token은 64자 hex（256 bit）
- `allowed_events`로 트리거 가능한 이벤트를 제한
- `allowed_events`가 빈 배열 = 전체 이벤트 허용
