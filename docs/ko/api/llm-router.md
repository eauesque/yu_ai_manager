# LLM Router API

YU AI Manager의 LLM Router는 여러 로컬 LLM 백엔드 (Ollama,
hailo-ollama 등)를 Anthropic Messages API 및 OpenAI Chat Completions
API 양쪽 프로토콜로 통합 인터페이스화합니다.

베이스 URL: `http://localhost:5000/v1`

## 엔드포인트

### POST /v1/messages

Anthropic Messages API 호환. Claude Code / Claude Desktop의
`ANTHROPIC_BASE_URL=http://localhost:5000/v1`로 접속 가능.

요청:
```json
{
  "model": "local-coder-big",
  "messages": [{"role": "user", "content": "..."}],
  "system": "...",
  "max_tokens": 1024,
  "stream": false
}
```

응답: Anthropic Messages 형식.

### POST /v1/chat/completions

OpenAI Chat Completions API 호환. Continue / Aider 등의 OpenAI 호환 클라이언트용.

### GET /v1/models

전체 백엔드의 전체 모델 + alias 목록을 OpenAI `/v1/models` 형식으로 반환.
`yu_metadata` 필드에 context_window / size_b / backend_status 등의 독자 정보.

### GET /v1/router/health

Router 자체의 상태와 백엔드 요약. 진단용.

### POST /v1/router/refresh

`{"backend": "ollama-mac"}`으로 단일 백엔드, 본문 없이 전체 백엔드의
discovery를 강제 재실행.

### POST /v1/router/estimate

토큰 수 추정 (tiktoken cl100k 근사).

### GET /v1/router/capabilities/{target}

모델의 good_at / weak_at / notes 등의 큐레이트된 메타데이터.

## 인증

`config.json`의 `llm_router.auth.mode`:

| mode | 동작 |
|---|---|
| `loopback` (default) | 127.0.0.1 / ::1만 무인증으로 허용 |
| `api_key` | `x-api-key` 또는 `Authorization: Bearer` 헤더 검증 |
| `none` | 인증 없음 |

상세는 `docs/ko/llm-router/setup.md` 참조.
