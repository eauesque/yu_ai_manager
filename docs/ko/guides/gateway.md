# Gateway — LAN 인증 경계 가이드

> 대상 버전: Gateway Phase 1 (v4.75.0 이상) / Gradio 추가 (v4.255.11 이상)

## Gateway란

Gateway는 SD WebUI・ComfyUI・Ollama・Gradio 앱 등의 **인증 기능이 없는 백엔드 도구**에 대한 액세스를
**Bearer 토큰 + 스코프 모델**로 일원 보호하는 리버스 프록시입니다.

```
외부 클라이언트 / LAN의 다른 머신
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │          scope 체크 ──► 백엔드 선택           │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### LLM Router와의 차이

| | Gateway | LLM Router |
|---|---|---|
| **대상** | SD WebUI・ComfyUI・Ollama・Gradio를 통합 | LLM (Ollama)만 |
| **인증** | scope 기반 Bearer 필수 | loopback은 우회 가능 |
| **프록시 대상** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | `/v1/*`만 |
| **주요 용도** | 외부 / LAN에 생성 도구를 안전하게 공개 | AI 코딩 도구의 백엔드 |

동일한 머신에서 둘을 동시에 활성화할 수도 있습니다.

---

## 세트업

### 1. 초기 API 키 생성 (CLI)

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

출력 예:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(이 시크릿은 한 번만 표시됩니다. 반드시 복사하세요)
```

### 2. config.json에 설정 추가

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> `secret_enc` 필드에는 CLI가 출력한 `enc:v2:...` 형식의 암호화된 값을 사용합니다.  
> 평문 시크릿은 `config.json`에 직접 쓰지 마세요.

### 3. 앱을 다시 시작하여 동작 확인

```bash
GW_HOST=<이 머신의 LAN IP>
GW_PORT=5000
BEARER=<api-key-secret>

# 인증 없음 → 401
curl -i http://$GW_HOST:$GW_PORT/v1/models

# 올바른 Bearer → 200
curl http://$GW_HOST:$GW_PORT/v1/models \n  -H "Authorization: Bearer $BEARER"

# 백엔드의 가동 상태
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \n  -H "Authorization: Bearer $BEARER"

# 노드 서비스 목록
curl http://$GW_HOST:$GW_PORT/v1/node/services \n  -H "Authorization: Bearer $BEARER"
```

---

## WebUI (/gateway 페이지)

`/gateway`에서 열 수 있는 관리 대시보드입니다.

### 백엔드 목록

등록된 백엔드의 가동 상태를 목록으로 표시합니다.

| 열 | 설명 |
|---|---|
| **타입** | 백엔드의 종류 (`ollama`, `sd_webui`, `comfyui`, `gradio`) |
| **포트** | 프록시 대상의 포트 번호 |
| **상태** | `online` / `offline` / `unknown` |
| **작업** | Probe (통신 확인) · 설정 변경 |

### 백엔드의 자동 스캔

「스캔」 버튼을 누르면 로컬의 일반적인 포트 (7860, 8188, 11434, 7861 등)를  
스캔하여 가동 중인 도구를 자동으로 감지해 등록을 제안합니다.

### API 키 관리

WebUI에서도 API 키의 추가・실효가 가능합니다 (`*` 스코프를 가진 키 필요).

---

## 스코프 목록

| 스코프 | 허용되는 엔드포인트 |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages` (Anthropic 호환) |
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` 등 |
| `sd:query` | `GET /sd/sdapi/v1/samplers` 등 |
| `sd:admin` | `POST /sd/sdapi/v1/options` 등 |
| `comfy:generate` | `POST /comfy/api/prompt` 등 |
| `comfy:query` | `GET /comfy/api/queue` 등 |
| `memory:read` | `GET /agentmemory/memories` 등 (읽기) |
| `memory:write` | `POST /agentmemory/observe` 등 (쓰기) |
| `memory:admin` | `POST /agentmemory/migrate` 등 (관리) |
| `ollama:proxy` | `GET/POST /ollama/<name>/*` (Ollama 네이티브 API + OpenAI 호환 전체 투과) |
| `gradio:proxy` | `GET/POST /gradio/<name>/*` (모든 엔드포인트 투과) |
| `gateway:admin` | API 키 관리・설정 변경 (loopback에서 자동 부여) |
| `node:status` | `GET /v1/node/services` |
| `*` | 모든 스코프 (관리자용) |

### 용도별 키의 예

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Ollama 프록시

LLM Router의 `/v1/*`와 별도로 Ollama 네이티브 API (`/api/*`) 및 OpenAI 호환 API (`/v1/*`)를  
그대로 투과 전송하는 프록시입니다. `OLLAMA_HOST`의 대상을 Gateway로 변경하면 인증이 추가됩니다.

### 프록시 URL

```
/ollama/<backend_name>/<subpath>  →  등록된 base_url의 /<subpath>로 전송
```

### 설정 예

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### 클라이언트 설정 (`OLLAMA_HOST` 방식)

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# 이후의 ollama 명령은 모두 Gateway를 거침
ollama list
ollama run llama3.3:70b
```

> `OLLAMA_HOST`에 Bearer를 전달할 수 없는 클라이언트는 `allow_loopback_bypass: true` +  
> loopback 경유로 키 없이 통과시키거나 `*` 스코프 키로 대신하세요.

### 대용량 파일 전송

모델 blob (`/api/blobs/*`)은 스트리밍 전송이므로 타임아웃이 없습니다 (다른 경로는 300초).  
GB 단위의 모델 풀・푸시도 문제없이 작동합니다.

---

## Gradio 프록시

Gradio 기반의 WebUI (Irodori-TTS 등)를 Gateway 경유로 인증이 추가된 액세스가 가능하게 합니다.  
모든 엔드포인트를 투과 전송하는 최소 구현입니다 (엔드포인트 제한 없음・50 MiB 바디 상한만).

### 프록시 URL

```
/gradio/<backend_name>/<subpath>  →  등록된 base_url의 /<subpath>로 전송
```

백엔드명 (`<backend_name>`)은 `config.json`의 `backends`에 등록한 키 이름입니다.

### 설정 예

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### 동작 확인

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Gradio 앱의 정보 취득
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Gradio 3.x 호환 predict
curl -H "Authorization: Bearer $KEY" \n  -X POST "$GW/gradio/irodori-tts/run/predict" \n  -H "Content-Type: application/json" \n  -d '{"data": ["Hello"], "fn_index": 0}'
```

### 제한 사항

- WebSocket (`/queue/join`)은 미지원 (HTTP만)
- Gradio 4.x의 SSE 스트림 (`GET /call/{api_name}/{event_id}`)은 전체 버퍼 전송이므로  
  장시간 생성에서는 타임아웃의 우려가 있습니다

---

## Agent Memory (agentmemory) 프록시

Gateway는 `@agentmemory/mcp` 등 agentmemory 클라이언트를  
LAN 거쳐도 안전하게 사용할 수 있는 프록시도 제공합니다.

### 엔드포인트

```
/agentmemory/livez       → 인증 불필요 (헬스 체크)
/agentmemory/health      → memory:read 스코프 필요
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（이후, 완전한 목록은 agentmemory 공식 API 참조）
```

### 동일 머신에서 사용하는 경우

`allow_loopback_bypass: true`일 때 loopback (127.0.0.1)에서는  
API 키 없이 그대로 통과합니다. MCP 설정의 변경은 **불필요**합니다.

### LAN의 다른 머신에서 사용하는 경우

`@agentmemory/mcp`는 환경 변수 `AGENTMEMORY_SECRET`을  
`Authorization: Bearer <secret>`으로 upstream에 보냅니다.

**MCP 설정 (`claude_desktop_config.json` / `.mcp.json`)의 변경 예:**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

필요한 스코프 (API 키 생성 시 지정):

```json
"scopes": ["memory:read", "memory:write"]
```

관리 작업 (`/migrate`・`/governance/*` 등)도 필요한 경우 `memory:admin`을 추가.

### 동작 확인

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# 인증 불필요 (livez)
curl $GW/agentmemory/livez

# Bearer로 memories 취득
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Basic 인증으로도 동작 (SD 클라이언트 호환)
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## 인증 모드

| 모드 | 동작 |
|---|---|
| `api_key` | Bearer 토큰이 필수 (`allow_loopback_bypass: true`로 loopback만 면제) |
| `loopback` | loopback (127.0.0.1)에서는 인증 불필요. LAN에서는 `api_key`와 동등 |
| `none` | 인증 없음 (개발・테스트 전용. 본번 불가) |

`allow_loopback_bypass: true`로 설정하면 동일 머신 위의 도구 (Claude Code CLI 등)는  
API 키 없이 Gateway를 통과할 수 있습니다.

---

## Health Probe

`health_probe.enabled: true`일 때 설정된 간격으로 백엔드에 자동 통신 확인을 실시합니다.

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

오프라인 백엔드는 `/v1/router/capabilities`의 `backends` 필드에서  
`"status": "offline"`으로 보고됩니다.

---

## 자주 있는 문제

| 증상 | 원인 / 대처 |
|---|---|
| 모든 요청이 401 | `allow_loopback_bypass`가 `false`로 loopback에서도 키 필요. 또는 Bearer 값이 잘못됨 |
| SD WebUI로의 프록시가 404 | `sd_webui.base_url`의 포트가 정확하지 않음 (기본값 7860). `/gateway`에서 Probe 실행 |
| ComfyUI WebSocket이 연결되지 않음 | `ws_url`을 설정했는지 확인 (`ws://127.0.0.1:8188/ws`) |
| Gradio 프록시가 404 | `backend_name`이 `config.json`의 backends 키 이름과 일치하는지 확인. `type: "gradio"` 지정도 필요 |
| Gradio의 SSE 스트림이 타임아웃 | 장시간 생성 (동영상 등)에서는 전체 버퍼 방식의 제한 있음. 단시간 추론 (TTS 등)은 문제 없음 |
| 스코프 부족으로 403 | 사용 중인 키의 스코프가 부족. `*` 스코프의 키로 API 키 관리에서 추가 |
| `allowed_models`로 특정 모델만 사용하게 하고 싶음 | `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]`처럼 배열로 지정 |

---

## 대상 외 (Phase 1 범위 외)

- 백엔드의 start/stop/restart (SSH + systemctl로 실시)
- `/v1/responses` (Codex 호환 façade) — Phase 2 이후
- 복수 Gateway 인스턴스의 부하 분산 — LAN Cowork의 분산 추론 활용

---

## 관련 문서

- [Gateway API 레퍼런스](../api/gateway.md) — `/api/gateway/*` 엔드포인트 상세
- [LLM Router 세트업](../llm-router/setup.md) — LLM 전용 경량 프록시
- [LAN Cowork 개요](../lan-cowork/README.md) — 복수 노드의 연계

## WebUI에서의 API 키 관리

설정 페이지의 **「Gateway API 키」** 탭에서 API 키의 생성・목록・삭제가 가능합니다.
[Gateway 페이지](/gateway)에도 링크가 있습니다.

### API 키 생성

1. **라벨**을 입력 (예: `Claude Desktop`) — ID는 자동으로 slug화 (예: `claude-desktop`)
2. **스코프**를 배지로 선택 (1개 이상 필수)
3. `*` (전체 허용) 선택 시 확인 체크박스에 체크
4. 「생성」 버튼을 클릭
5. 표시된 시크릿을 복사 — **이 화면을 떠나면 다시는 표시되지 않습니다**

### 주의 사항

- `*` 스코프를 가진 마지막 키는 삭제할 수 없습니다 (Bearer 경로 lockout 방지)
- 먼저 다른 `*` 키를 생성한 후 삭제하세요

### 사용 방법

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```
