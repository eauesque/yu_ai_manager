# API: /api/llm_router (Admin)

LLM Router의 관리 조작용 엔드포인트 모음. 일반적인 WebUI 세션 인증 (PIN/세션)으로 보호되며, OpenAI 호환 `/v1/*` 서피스와는 완전히 분리되어 있습니다.

> **주의**: 이것은 관리용 엔드포인트이며, LLM 추론 요청을 수행하는 `/v1/chat/completions` 등과는 별개입니다.

---

## 공통 응답 형식

전체 엔드포인트는 `api_result` 래퍼를 사용합니다. 성공 시 본문은 `data` 키 하위에 네스트됩니다.

```json
{
  "status": "ok",
  "data": { ... }
}
```

에러 시:

```json
{
  "status": "error",
  "error": "에러 설명"
}
```

---

## GET /api/llm_router/status

대시보드 전체를 1개 요청으로 렌더링하기 위한 스냅샷. 전체 백엔드 정보 및 에일리어스 맵을 반환합니다.

### 요청

```
GET /api/llm_router/status
```

파라미터 없음.

### 응답 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### 필드 설명

**`router`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `version` | string | 라우터의 스키마 버전 (현재 `"1.0.0"`) |
| `alias_count` | int | 정의된 에일리어스 수 |

**`backends[]`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `alias` | string | 백엔드의 고유 식별자 |
| `base_url` | string | OpenAI 호환 엔드포인트의 베이스 URL |
| `source` | string | `"static"` (설정 파일) 또는 `"mdns"` (자동 발견) |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true`인 경우 라우팅 대상 외 |
| `model_count` | int | 공개 모델 수 |
| `models[]` | array | 모델 목록 (`name`, `context_window`, `size_b`) |
| `last_seen` | string \| null | 마지막 정상 연결 일시 (ISO 8601) |
| `last_error` | string \| null | 마지막 에러 메시지 |

**`aliases`**

논리 에일리어스명 → 물리 모델 ID (`백엔드alias/모델명`)의 맵.

---

## POST /api/llm_router/refresh

전체 백엔드 또는 지정 백엔드에 대해 강제 프로브를 실행하고, `status` 및 모델 목록을 갱신합니다.

### 요청

**전체 백엔드를 갱신하는 경우 (본문 없음):**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

또는 Content-Type 헤더 없이 빈 본문도 가능.

**특정 백엔드만 갱신하는 경우:**

```json
{
  "alias": "ollama-mac"
}
```

### 응답 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

`refreshed` 배열의 각 요소는 경량 갱신 결과만 포함합니다 (전체 필드는 `/status`에서 취득).

### 에러 `404 Not Found`

`alias`를 지정했지만 존재하지 않는 경우:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 비고

- 프로브는 동기적으로 실행됨 (완료까지 대기 후 응답 반환)
- `disabled: true`인 백엔드에 대해서도 프로브는 실행됨 (status가 갱신됨)
- mDNS 유래 백엔드도 대상

---

## POST /api/llm_router/backends/`<alias>`/disable

지정 백엔드를 비활성화합니다. 비활성화된 백엔드는 라우팅에서 제외되며, `data/llm_router_state.json`에 영구 저장됩니다.

### 요청

```
POST /api/llm_router/backends/ollama-mac/disable
```

본문 불필요.

### 응답 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### 에러 `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 에러 `500 Internal Server Error`

디스크 영구화에 실패한 경우 (권한 에러, 디스크 풀 등). 인메모리 상태는 롤백됩니다.

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### 영구화 구조

1. 인메모리 카탈로그의 `disabled` 플래그를 `true`로 설정
2. `data/llm_router_state.json`을 아토믹 기록 (`.tmp` 경유로 `os.replace`)
3. 기록 실패 시 스텝 1을 롤백하고 `500`을 반환

앱 재시작 후에도 비활성화 상태가 유지됩니다. mDNS로 동적 발견되는 백엔드가 시작 전에 disable된 경우에도, 발견 후 자동으로 disabled 상태가 적용됩니다.

---

## POST /api/llm_router/backends/`<alias>`/enable

지정 백엔드를 활성화합니다. `disable`의 역조작입니다.

### 요청

```
POST /api/llm_router/backends/ollama-mac/enable
```

본문 불필요.

### 응답 `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### 에러

`disable` 엔드포인트와 동일 (`404` / `500`). `disabled: false`로 영구화됩니다.

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/api/llm_router/status` | 전체 백엔드 및 에일리어스의 스냅샷 취득 |
| `POST` | `/api/llm_router/refresh` | 전체 또는 개별 백엔드의 강제 프로브 |
| `POST` | `/api/llm_router/backends/<alias>/disable` | 백엔드 비활성화 (영구화 포함) |
| `POST` | `/api/llm_router/backends/<alias>/enable` | 백엔드 활성화 (영구화 포함) |

## 관련 문서

- [LLM Router WebUI 가이드](../llm-router/webui.md)
- [LLM Router 설정](../llm-router/setup.md)
