# Tagger Server Registry API

여러 태그 추론 워커(Hailo Remote, ONNX Local, Ryzen AI 등)를 통합 클러스터로 관리하고, 공유 큐 워크스틸링 병렬 실행 모델로 분산 배치 태깅을 수행하는 API입니다.

## 개요

Tagger Server Registry는 단일 Hailo Remote Tagger를 넘어 여러 이종 추론 백엔드를 클러스터로 관리합니다. 각 서버에는 설정 가능한 우선순위가 있으며, 선택한 분산 모드(single / parallel / idle_first)에 따라 작업이 분배됩니다.

### 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                   eauesque Host                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         Tagger Orchestrator                  │   │
│  │  - Shared queue (work-stealing)              │   │
│  │  - Progress aggregation -> JobManager -> SSE │   │
│  └──────────┬──────────────┬──────────────────┘   │
│    ┌────────▼───┐   ┌──────▼────────────┐          │
│    │ Local ONNX │   │ Hailo HTTP Client │          │
│    │ Worker     │   │ Worker            │          │
│    └────────────┘   └──────────┬────────┘          │
└────────────────────────────────│────────────────────┘
              ┌──────────────────┼──────────────────┐
     ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
     │ Pi A       │    │ Pi B       │    │ Future     │
     │ Hailo 10H  │    │ Hailo 10H  │    │ NPU Server │
     └────────────┘    └────────────┘    └────────────┘
```

### 서버 유형

| 유형 | 설명 |
|------|------|
| `hailo_remote` | Hailo-10H 탑재 원격 장치 (예: Raspberry Pi 5) |
| `onnx_local` | 로컬 ONNX Runtime 추론 |
| `onnx_remote` | 원격 ONNX 추론 서버 |
| `ryzen_ai` | AMD Ryzen AI NPU |

### 분산 모드

| 모드 | 설명 |
|------|------|
| `single` | 최고 우선순위의 활성 서버 1대만 사용 |
| `parallel` | 모든 활성 서버에서 병렬 실행 (워크스틸링) |
| `idle_first` | 유휴 상태의 서버를 우선 사용 |

---

## 서버 엔트리 형식

```json
{
  "id": "pi-hailo-a",
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "priority": 10,
  "enabled": true,
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "bearer_token": "enc:gAAAAABm...",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 서버 식별자 (자동 생성 또는 수동 지정) |
| `name` | string | 표시 이름 |
| `type` | string | 서버 유형 (`hailo_remote` / `onnx_local` / `onnx_remote` / `ryzen_ai`) |
| `priority` | int | 우선순위 (낮을수록 높은 우선순위, 기본값: 50) |
| `enabled` | bool | 활성/비활성 |
| `config` | object | 유형별 설정 (아래 참조) |

### config 필드 (원격 서버용)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `endpoint_url` | string | 예 | 원격 서버 URL |
| `bearer_token` | string | 아니오 | Bearer 토큰 (저장 시 자동 암호화 `enc:` 접두사) |
| `threshold` | float | 아니오 | 태그 신뢰도 임계값 (기본값: 0.35) |
| `timeout` | int | 아니오 | 요청 타임아웃 초 (기본값: 30) |

---

## 인증

원격 서버(`hailo_remote` / `onnx_remote`)와의 통신은 선택적으로 Bearer 토큰 인증을 지원합니다.

### 호스트 → 원격 서버

`config.bearer_token`이 설정되면, 모든 HTTP 요청(상태 확인 및 태깅)에 `Authorization: Bearer <token>` 헤더가 자동으로 포함됩니다. 토큰은 `config.json`에 Fernet 암호화(`enc:` 접두사)로 저장되며, API 응답에서는 마스킹 처리됩니다.

### 원격 서버 측

`deploy/hailo_tagger_server.py`는 토큰 검증이 포함된 참조 구현을 제공합니다. 시작 시 다음 방법 중 하나로 토큰을 설정할 수 있습니다:

```bash
# 명령줄 인수
python hailo_tagger_server.py --token "my-secret-token"

# 파일에서 읽기
python hailo_tagger_server.py --token-file /etc/tagger/token

# 환경 변수
TAGGER_BEARER_TOKEN=my-secret-token python hailo_tagger_server.py
```

토큰이 설정되지 않은 경우, 서버는 이전 버전과의 호환성을 위해 개방 접근 모드(LAN 내 신뢰 모델)로 작동합니다. 잘못된 토큰에는 401/403 응답이 반환됩니다.

---

## GET /api/tagger-servers

등록된 서버 목록과 현재 분산 모드를 조회합니다.

### 속도 제한

READ (무제한)

### 응답

```json
{
  "ok": true,
  "data": {
    "servers": [
      {
        "id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "priority": 10,
        "enabled": true,
        "config": {
          "endpoint_url": "http://192.168.1.101:8080",
          "threshold": 0.35,
          "timeout": 30
        }
      }
    ],
    "mode": "parallel"
  }
}
```

---

## POST /api/tagger-servers

새로운 태거 서버를 추가합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 표시 이름 |
| `type` | string | 예 | 서버 유형 |
| `config` | object | 예 | 유형별 설정 |
| `priority` | int | 아니오 | 우선순위 (기본값: 50) |
| `enabled` | bool | 아니오 | 활성/비활성 (기본값: `true`) |

### 요청 예시

```json
{
  "name": "Pi5 Hailo A",
  "type": "hailo_remote",
  "config": {
    "endpoint_url": "http://192.168.1.101:8080",
    "threshold": 0.35,
    "timeout": 30
  },
  "priority": 10
}
```

### 응답

```json
{
  "ok": true,
  "data": {
    "server": {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 필수 필드 누락 또는 유효하지 않은 유형 |

---

## PUT /api/tagger-servers/{server_id}

기존 서버의 설정을 업데이트합니다. 부분 업데이트를 지원합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 경로 파라미터

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `server_id` | string | 대상 서버 ID |

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 아니오 | 표시 이름 |
| `type` | string | 아니오 | 서버 유형 |
| `config` | object | 아니오 | 유형별 설정 |
| `priority` | int | 아니오 | 우선순위 |
| `enabled` | bool | 아니오 | 활성/비활성 |

### 응답

```json
{
  "ok": true,
  "data": {
    "server": { "..." }
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 404 | 서버를 찾을 수 없음 |

---

## DELETE /api/tagger-servers/{server_id}

서버를 삭제합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 경로 파라미터

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `server_id` | string | 대상 서버 ID |

### 응답

```json
{
  "ok": true,
  "data": {
    "deleted": "pi-hailo-a"
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 404 | 서버를 찾을 수 없음 |

---

## POST /api/tagger-servers/reorder

서버 우선순위를 일괄 재정렬합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `order` | string[] | 예 | 우선순위 순서의 서버 ID 배열 |

### 요청 예시

```json
{
  "order": ["pi-hailo-a", "local-onnx", "pi-hailo-b"]
}
```

### 응답

```json
{
  "ok": true,
  "data": {
    "servers": [ "..." ]
  }
}
```

---

## POST /api/tagger-servers/mode

분산 모드를 변경합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `mode` | string | 예 | `single` / `parallel` / `idle_first` |

### 응답

```json
{
  "ok": true,
  "data": {
    "mode": "parallel"
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 유효하지 않은 모드 값 |

---

## POST /api/tagger-servers/{server_id}/test

지정된 서버와의 연결을 테스트합니다.

### 속도 제한

HEAVY (~20 req/min, burst 5)

### 경로 파라미터

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `server_id` | string | 대상 서버 ID |

### 응답 (성공)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": true,
    "latency_ms": 45
  }
}
```

### 응답 (연결 불가)

```json
{
  "ok": true,
  "data": {
    "server_id": "pi-hailo-a",
    "reachable": false,
    "reason": "Connection refused"
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 404 | 서버를 찾을 수 없음 |

---

## GET /api/tagger-servers/health

모든 활성 서버의 상태를 확인합니다.

### 속도 제한

READ (무제한)

### 응답

```json
{
  "ok": true,
  "data": {
    "results": [
      {
        "server_id": "pi-hailo-a",
        "name": "Pi5 Hailo A",
        "type": "hailo_remote",
        "reachable": true,
        "latency_ms": 45
      },
      {
        "server_id": "local-onnx",
        "name": "Local ONNX",
        "type": "onnx_local",
        "reachable": true,
        "latency_ms": 2
      }
    ]
  }
}
```

---

## POST /api/tagger-servers/batch

공유 큐 워크스틸링 모델을 사용하여 분산 배치 태깅을 실행합니다. 백그라운드 작업으로 실행되며, 진행 상황은 SSE를 통해 알림됩니다.

### 속도 제한

HEAVY (~20 req/min, burst 5)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file_ids` | int[] | 아니오 | 대상 파일 ID 목록. 생략 시 미태깅 파일을 자동 선택 |
| `limit` | int | 아니오 | 자동 선택 시 최대 수량 (기본값: 500) |
| `force` | bool | 아니오 | 기존 태그 덮어쓰기 (기본값: `false`) |
| `threshold` | float | 아니오 | 태그 신뢰도 임계값 재정의 (생략 시 각 서버 설정 사용) |

### 요청 예시

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false,
  "threshold": 0.35
}
```

### 응답

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "tagger_servers_batch",
    "total_files": 5,
    "active_servers": ["pi-hailo-a", "local-onnx"]
  }
}
```

### 오류

| 상태 코드 | 코드 | 설명 |
|-----------|------|------|
| 400 | `no_servers` | 사용 가능한 활성 서버 없음 |
| 400 | `batch_too_large` | file_ids가 상한 초과 |
| 409 | `job_running` | 배치 작업이 이미 실행 중 |

---

## POST /api/tagger-servers/batch/cancel

실행 중인 태거 클러스터 배치 작업을 취소합니다.

### Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"cancelling"` |
| `message` | string | 상태 메시지 |

### Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 404 | `job_not_running` | 취소할 배치 작업이 실행되고 있지 않습니다 |

---

## GET /api/tagger-servers/tags/{file_id}

파일의 태거 태그를 조회합니다.

### 속도 제한

READ (무제한)

### 경로 파라미터

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `file_id` | int | 대상 파일의 데이터베이스 ID |

### 응답

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote:pi-hailo-a", "created_at": 1710720000}
    ]
  }
}
```

`source` 필드는 `{type}:{server_id}` 형식을 사용합니다 (예: `hailo_remote:pi-hailo-a`, `onnx_local:local-onnx`).

---

## DELETE /api/tagger-servers/tags/{file_id}

파일의 모든 태거 태그를 삭제합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 경로 파라미터

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `file_id` | int | 대상 파일의 데이터베이스 ID |

### 응답

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## GET /api/tagger-servers/stats

태거 통계 정보를 조회합니다.

### 속도 제한

READ (무제한)

### 응답

```json
{
  "ok": true,
  "data": {
    "total_files": 10000,
    "tagged_files": 8500,
    "untagged_files": 1500,
    "servers": {
      "pi-hailo-a": {"tagged": 5000, "type": "hailo_remote"},
      "local-onnx": {"tagged": 3500, "type": "onnx_local"}
    }
  }
}
```

---

## POST /api/tagger-servers/migrate

레거시 `hailo_tagger` 설정을 Tagger Server Registry 형식으로 마이그레이션합니다. `config.json`의 기존 `hailo_tagger` 항목을 `tagger_servers` 배열 항목으로 변환합니다.

### 속도 제한

DESTRUCTIVE (~12 req/min, burst 3)

### 응답

```json
{
  "ok": true,
  "data": {
    "migrated": true,
    "server": {
      "id": "legacy-hailo",
      "name": "Hailo Remote (migrated)",
      "type": "hailo_remote",
      "priority": 50,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.50:8080",
        "threshold": 0.35,
        "timeout": 30
      }
    }
  }
}
```

### 응답 (마이그레이션 불필요)

```json
{
  "ok": true,
  "data": {
    "migrated": false,
    "reason": "No legacy config found"
  }
}
```

---

## 설정

`config.json`의 관련 키:

```json
{
  "tagger_servers": [
    {
      "id": "pi-hailo-a",
      "name": "Pi5 Hailo A",
      "type": "hailo_remote",
      "priority": 10,
      "enabled": true,
      "config": {
        "endpoint_url": "http://192.168.1.101:8080",
        "bearer_token": "enc:gAAAAABm...",
        "threshold": 0.35,
        "timeout": 30
      }
    },
    {
      "id": "local-onnx",
      "name": "Local ONNX",
      "type": "onnx_local",
      "priority": 20,
      "enabled": true,
      "config": {
        "threshold": 0.35
      }
    }
  ],
  "tagger_servers_mode": "parallel"
}
```

| 키 | 타입 | 설명 |
|----|------|------|
| `tagger_servers` | array | 서버 엔트리 배열 |
| `tagger_servers_mode` | string | 분산 모드 (`single` / `parallel` / `idle_first`) |

설정 페이지(Settings)에서도 변경할 수 있습니다.

---

## DB 스키마

태그는 `file_hailo_tags` 테이블에 저장됩니다. `source` 컬럼은 `{type}:{server_id}` 형식을 사용하여 어떤 서버가 태그를 부여했는지 식별합니다.

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| 컬럼 | 설명 |
|------|------|
| `file_id` | files 테이블의 외래 키 |
| `tag_name` | Danbooru 태그 이름 (예: `1girl`, `solo`) |
| `confidence` | 추론 신뢰도 (0.0~1.0) |
| `source` | 태그 소스 식별자 (`{type}:{server_id}` 형식, 예: `hailo_remote:pi-hailo-a`) |
| `created_at` | UNIX 타임스탬프 |
