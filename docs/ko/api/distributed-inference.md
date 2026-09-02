# 분산 추론 API

분산 추론 서버 레지스트리의 REST API. 공유 큐 방식을 사용하여 CLIP 시맨틱 인덱싱 워크로드를 여러 노드에 분산합니다.

## 엔드포인트 목록

### GET /api/inference-servers

등록된 서버 목록과 현재 디스패치 모드를 반환합니다.

**응답:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: 서버 설정 객체 배열

---

### POST /api/inference-servers

새 추론 서버를 등록합니다.

**요청 본문:**

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `name` | string | ✓ | — | 표시 이름 |
| `endpoint_url` | string | ✓ | — | Worker 기본 URL |
| `inference_types` | string[] | — | `["clip"]` | 지원 추론 타입 |
| `priority` | int | — | `50` | 우선순위 (낮은 값이 높은 우선순위) |
| `bearer_token` | string | — | — | 인증 토큰 |
| `timeout` | int | — | `30` | 요청 타임아웃(초) |

**응답:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

기존 서버 설정을 업데이트합니다. 요청 본문은 POST와 동일한 필드를 부분적으로 지정할 수 있습니다.

---

### DELETE /api/inference-servers/{server_id}

레지스트리에서 서버를 제거합니다.

**응답:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

지정한 서버에 대해 헬스 체크를 실행합니다.

**응답:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

활성화된 모든 서버에 대해 헬스 체크를 일괄 실행합니다.

**응답:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

디스패치 모드를 설정합니다.

**요청 본문:**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**응답:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## 디스패치 모드

| 모드 | 설명 |
|---|---|
| `single` | 우선순위가 가장 높은(priority 값이 가장 낮은) 서버만 사용 |
| `parallel` | 공유 큐 방식으로 모든 활성 서버에 분산 처리 |
| `idle_first` | 헬스 체크 후 응답 가능한 서버에만 병렬 처리 |

## 분산 시맨틱 인덱싱

시맨틱 검색 확장의 `POST /api/index/start` 요청 본문에 `distributed: true`를 추가하면 등록된 Worker 서버를 활용한 분산 인덱싱이 활성화됩니다.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Worker 서버 설정

```bash
python deploy/hailo_tagger_server.py --port 9090
```

지원 엔드포인트:

| 경로 | 설명 |
|---|---|
| `GET /health` | 헬스 체크 |
| `POST /tag` | WD-Tagger 추론 |
| `POST /clip-encode` | CLIP 벡터 인코딩 |

## MCP 도구

| 도구명 | 설명 |
|---|---|
| `inference-servers-list` | 서버 목록 및 현재 모드 조회 |
| `inference-server-add` | 서버 추가 |
| `inference-server-update` | 서버 설정 업데이트 |
| `inference-server-remove` | 서버 제거 |
| `inference-server-health` | 헬스 체크 실행 |
| `inference-dispatch-mode-set` | 디스패치 모드 설정 |
