# Gateway API 참조

## 인증

루프백 우회 경로를 제외한 모든 엔드포인트에 다음이 필요합니다:
```
Authorization: Bearer <api_key>
```

## LLM 엔드포인트

| 메서드 | 경로 | Scope | 설명 |
|--------|------|-------|------|
| POST | /v1/chat/completions | llm:chat | OpenAI 호환 채팅 |
| POST | /v1/messages | llm:messages | Anthropic Messages API |
| GET | /v1/models | llm:models | 사용 가능한 모델 목록 |
| GET | /v1/router/capabilities | (인증만) | Gateway capabilities |

## SD WebUI 엔드포인트

| 메서드 | 경로 | Scope |
|--------|------|-------|
| POST | /sd/sdapi/v1/txt2img | sd:generate |
| POST | /sd/sdapi/v1/img2img | sd:generate |
| GET | /sd/sdapi/v1/samplers | sd:query |
| GET | /sd/sdapi/v1/sd-models | sd:query |
| GET | /sd/sdapi/v1/options | sd:admin |
| POST | /sd/sdapi/v1/options | sd:admin |

## ComfyUI 엔드포인트

| 메서드 | 경로 | Scope |
|--------|------|-------|
| POST | /comfy/api/prompt | comfy:generate |
| GET | /comfy/api/queue | comfy:query |
| GET | /comfy/api/history | comfy:query |
| GET | /comfy/api/view | comfy:query |
| WS | /comfy/ws | comfy:generate |

## 상태 엔드포인트

| 메서드 | 경로 | Scope |
|--------|------|-------|
| GET | /v1/node/services | node:status |

## 관리 API

| 메서드 | 경로 | Scope | 설명 |
|--------|------|-------|------|
| POST | /api/gateway/keys | * | 키 생성 (secret은 한 번만 표시) |
| GET | /api/gateway/keys | * | 키 목록 (secret 없음) |
| PATCH | /api/gateway/keys/{id} | * | scope/models 업데이트 |
| DELETE | /api/gateway/keys/{id} | * | 키 삭제 |
| POST | /api/gateway/auth/reload | * | 설정 핫 리로드 |

## 오류 형식

```json
{
  "error": {
    "message": "...",
    "type": "authentication_error | invalid_request_error | server_error",
    "code": "invalid_api_key | insufficient_scope | model_not_found | backend_unavailable | path_traversal | body_too_large",
    "param": "..."
  }
}
```
