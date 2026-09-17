# AI Analysis API

AI 기반 이미지 분석, 프롬프트 트렌드 분석 및 서버 관리를 위한 API입니다.

모든 POST/PUT/DELETE 엔드포인트는 `X-Requested-With` 헤더가 필요합니다 (Bearer API Key 사용 시 불필요).

## 속도 제한

`/api/analysis/` 하위의 쓰기 엔드포인트는 **HEAVY** 티어를 사용합니다 (약 20회/분, 버스트 5). GET 엔드포인트는 무제한입니다.

---

## 설정

### GET /api/analysis/config

현재 AI 분석 설정을 가져옵니다. API Key는 마스킹되어 반환됩니다.

#### 응답

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `engine` | string | 현재 엔진 타입 (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude API Key (마스킹) |
| `model` | string | Claude API 모델명 |
| `ollama_url` | string | Ollama 서버 URL |
| `ollama_model` | string | Ollama 모델명 |
| `openai_api_key` | string | OpenAI API Key (마스킹) |
| `openai_model` | string | OpenAI 모델명 |
| `openai_compat_url` | string | OpenAI 호환 서버 URL |
| `openai_compat_api_key` | string | OpenAI 호환 API Key (마스킹) |
| `openai_compat_model` | string | OpenAI 호환 모델명 |
| `hailo_vlm_model` | string | Hailo VLM 모델명 |
| `fallback_local_only` | boolean | 로컬 엔진만 사용할지 여부 |
| `language` | string | 분석 결과 언어 (`ja`, `en` 등) |
| `is_local` | boolean | 현재 엔진이 로컬(무료)인지 여부 |
| `has_servers` | boolean | 서버 레지스트리 설정 여부 |
| `servers` | array | 서버 목록 (`has_servers`가 true일 때만) |
| `active_server` | string | 활성 서버 ID (`has_servers`가 true일 때만) |

### POST /api/analysis/config

AI 분석 설정을 저장합니다. 마스킹된 값(`...`을 포함하는 문자열)은 덮어쓰지 않습니다. API Key는 자동으로 암호화됩니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `engine` | string | 아니오 | 엔진 타입 |
| `api_key` | string | 아니오 | Claude API Key |
| `model` | string | 아니오 | Claude API 모델 |
| `ollama_url` | string | 아니오 | Ollama 서버 URL |
| `ollama_model` | string | 아니오 | Ollama 모델명 |
| `openai_api_key` | string | 아니오 | OpenAI API Key |
| `openai_model` | string | 아니오 | OpenAI 모델명 |
| `openai_compat_url` | string | 아니오 | OpenAI 호환 서버 URL |
| `openai_compat_api_key` | string | 아니오 | OpenAI 호환 API Key |
| `openai_compat_model` | string | 아니오 | OpenAI 호환 모델명 |
| `hailo_vlm_model` | string | 아니오 | Hailo VLM 모델명 |
| `fallback_local_only` | boolean | 아니오 | 로컬 엔진만 사용 |
| `language` | string | 아니오 | 분석 결과 언어 |

#### 응답

```json
{
  "success": true
}
```

---

## 엔진 탐색

### GET /api/analysis/available-engines

설정되고 연결 가능한 엔진 목록을 가져옵니다. `fallback_local_only` 활성화 시 클라우드 엔진은 제외됩니다.

#### 응답

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `engines[].type` | string | 엔진 타입 식별자 |
| `engines[].label` | string | 표시 라벨 |
| `engines[].model` | string | 현재 설정된 모델 |
| `engines[].models` | string[] | 사용 가능한 모델 목록 |

---

## 단일 파일 분석

### POST /api/analysis/analyze/\<file_id\>

AI 엔진으로 단일 파일을 분석합니다. 이미지, 동영상, 아카이브 내 이미지를 지원합니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `file_id` | int | 파일 ID (경로 매개변수) |

#### 요청

JSON 본문은 선택사항입니다. 생략 시 기본 설정이 사용됩니다.

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `mode` | string | 아니오 | 분석 모드. 기본값 `"full"` |
| `engine` | string | 아니오 | 엔진 타입 재정의 |
| `model` | string | 아니오 | 모델명 재정의 |
| `server_id` | string | 아니오 | 사용할 서버 ID 지정 |

#### 응답 (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### 오류 응답

- `400`: 엔진 미설정 / 지정한 엔진 무효
- `404`: 파일을 찾을 수 없음 / 디스크에 파일이 존재하지 않음
- `500`: 분석 중 오류 발생

### GET /api/analysis/result/\<file_id\>

파일의 저장된 분석 결과를 가져옵니다. 여러 엔진/모드가 사용된 경우 모든 결과를 반환합니다.

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `file_id` | int | 파일 ID (경로 매개변수) |

#### 응답 (200) -- 결과 있음

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `found` | boolean | 분석 결과 존재 여부 |
| `result` | object | 가장 최근 분석 결과 (하위 호환용) |
| `results` | array | 모든 분석 결과 배열 |

#### 응답 (200) -- 결과 없음

```json
{
  "found": false
}
```

---

## 일괄 분석

### POST /api/analysis/batch

미분석 파일에 대한 일괄 AI 분석 작업을 시작합니다. 백그라운드에서 실행됩니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `limit` | int | 아니오 | 분석할 최대 파일 수. 기본값 10. 클라우드 엔진은 최대 10. 로컬 엔진은 0으로 설정하면 전부 |
| `scan_root` | string | 아니오 | 특정 스캔 루트로 대상 제한 |
| `file_ids` | int[] | 아니오 | 분석할 파일 ID를 직접 지정 |
| `server_ids` | string[] | 아니오 | 사용할 서버 ID. 여러 서버로 병렬 분석 가능 |

#### 응답 (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `started` | boolean | 작업 시작 여부 |
| `count` | int | 분석할 파일 수 |
| `parallel` | boolean | 병렬 실행 여부 (여러 `server_ids`) |
| `worker` | boolean | 추론 워커를 통해 디스패치된 경우 true |
| `subprocess` | boolean | 서브프로세스로 실행 중인 경우 (Hailo VLM) true |

#### 오류 응답

- `400`: 분석할 파일 없음
- `409`: AI 분석 작업이 이미 실행 중

### POST /api/analysis/batch/cancel

실행 중인 일괄 AI 분석 작업을 취소합니다.

#### 속도 제한

HEAVY

#### 요청

본문 불필요.

#### 응답 (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### 오류 응답

- `404`: 실행 중인 AI 분석 작업 없음

---

## 프롬프트 트렌드 분석

### POST /api/analysis/trends

최근 50개 프롬프트에 대해 트렌드 분석을 실행합니다. 결과는 자동으로 이력에 저장됩니다.

#### 속도 제한

HEAVY

#### 요청

본문 불필요.

#### 응답 (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### 오류 응답

- `400`: API Key 미설정 (클라우드 엔진 사용 시)
- `500`: 트렌드 분석 중 오류 발생

### GET /api/analysis/trends/history

프롬프트 트렌드 분석 이력을 가져옵니다. 최신순 정렬. 최대 50건 보관.

#### 매개변수

| 매개변수 | 타입 | 기본값 | 설명 |
|-----------|------|---------|-------------|
| `limit` | int | 20 | 가져올 건수 (최대 50) |
| `offset` | int | 0 | 오프셋 |

#### 응답

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `items[].id` | int | 이력 ID |
| `items[].engine` | string | 사용된 엔진 타입 |
| `items[].analyzed_at` | int | 분석 UNIX 타임스탬프 |
| `items[].prompt_count` | int | 분석된 프롬프트 수 |
| `items[].result` | object | 트렌드 분석 결과 |

### DELETE /api/analysis/trends/history/\<history_id\>

단일 트렌드 분석 이력 항목을 삭제합니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `history_id` | int | 이력 ID (경로 매개변수) |

#### 응답

```json
{
  "deleted": true
}
```

#### 오류 응답

- `404`: 이력을 찾을 수 없음

---

## 통계

### GET /api/analysis/stats

AI 분석 통계를 가져옵니다.

#### 응답

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `total_analyzed` | int | 분석된 파일 수 |
| `total_files` | int | 총 파일 수 (삭제 제외) |
| `styles` | array | 스타일 분포 (상위 10개) |
| `styles[].style` | string | 스타일 이름 |
| `styles[].count` | int | 파일 수 |
| `quality_distribution` | array | 품질 점수 분포 |
| `quality_distribution[].tier` | string | 품질 등급 (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | 파일 수 |
| `quality_distribution[].avg_score` | float | 평균 점수 |

---

## Ollama 연결

### GET /api/analysis/ollama/models

설정된 Ollama 서버에 연결하여 사용 가능한 모델을 나열합니다.

#### 응답

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 오류 응답

- `400`: Ollama URL 무효

### POST /api/analysis/ollama/test

지정된 URL의 Ollama 서버에 연결을 테스트합니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `ollama_url` | string | 예 | 테스트할 Ollama 서버 URL |

#### 응답

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### 오류 응답

- `400`: URL이 비어 있음 / URL 무효

---

## OpenAI 호환 서버 연결

### GET /api/analysis/openai-compat/models

설정된 OpenAI 호환 서버에 연결하여 사용 가능한 모델을 나열합니다.

#### 응답

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 오류 응답

- `400`: URL 미설정 / URL 무효

### POST /api/analysis/openai-compat/test

지정된 URL의 OpenAI 호환 서버에 연결을 테스트합니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `url` | string | 예 | 테스트할 URL |
| `api_key` | string | 아니오 | API Key (필요한 경우) |

#### 응답

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### 오류 응답

- `400`: URL이 비어 있음 / URL 무효

---

## AI 서버 레지스트리

우선순위 기반 폴백과 병렬 분석을 지원하는 여러 AI 서버를 등록하고 관리합니다.

### GET /api/analysis/servers

등록된 모든 서버와 상태를 나열합니다. API Key는 마스킹됩니다.

#### 응답

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `servers[].id` | string | 서버 ID (변경 불가) |
| `servers[].name` | string | 표시 이름 |
| `servers[].type` | string | 엔진 타입 (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | 우선순위 (낮을수록 높은 우선순위) |
| `servers[].enabled` | boolean | 활성화/비활성화 |
| `servers[].config` | object | 엔진별 설정 |
| `servers[].is_active` | boolean | 현재 활성 서버인지 여부 |
| `servers[].status` | string | 연결 상태 (목록 뷰에서는 항상 `"unknown"`) |

### POST /api/analysis/servers

새 서버를 등록합니다. 첫 번째 서버는 자동으로 활성으로 설정됩니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `name` | string | 예 | 서버 이름 |
| `type` | string | 예 | 엔진 타입 |
| `config` | object | 예 | 엔진별 설정 |
| `priority` | int | 아니오 | 우선순위 |
| `enabled` | boolean | 아니오 | 활성화/비활성화. 기본값 true |

#### 응답 (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### 오류 응답

- `400`: 유효성 검사 오류 / 서버 제한 도달

### PUT /api/analysis/servers/\<server_id\>

서버 설정을 업데이트합니다. `id` 필드는 변경할 수 없습니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `server_id` | string | 서버 ID (경로 매개변수) |

#### 요청

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

모든 필드는 선택사항입니다. 지정된 필드만 업데이트됩니다.

#### 응답

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### 오류 응답

- `400`: 타입 무효 / 서버를 찾을 수 없음

### DELETE /api/analysis/servers/\<server_id\>

서버를 삭제합니다. 활성 서버가 삭제되면 다음으로 높은 우선순위의 서버가 자동으로 활성화됩니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `server_id` | string | 서버 ID (경로 매개변수) |

#### 응답

```json
{
  "success": true
}
```

#### 오류 응답

- `400`: 서버를 찾을 수 없음

### POST /api/analysis/servers/\<server_id\>/activate

활성 서버를 전환합니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `server_id` | string | 서버 ID (경로 매개변수) |

#### 응답

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### 오류 응답

- `400`: 서버를 찾을 수 없음

### POST /api/analysis/servers/\<server_id\>/test

서버에 연결 테스트를 실행합니다. 응답 시간도 측정합니다.

#### 속도 제한

HEAVY

#### 매개변수

| 매개변수 | 타입 | 설명 |
|-----------|------|-------------|
| `server_id` | string | 서버 ID (경로 매개변수) |

#### 응답

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `available` | boolean | 서버 연결 가능 여부 |
| `elapsed_ms` | int | 연결 테스트 응답 시간 (밀리초) |
| `server` | object | 서버 정보 |

#### 오류 응답

- `400`: 서버를 찾을 수 없음

### PUT /api/analysis/servers/reorder

서버 우선순위를 일괄 업데이트합니다.

#### 속도 제한

HEAVY

#### 요청

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `server_ids` | string[] | 예 | 서버 ID 배열. 지정된 순서가 새로운 우선순위가 됨 |

#### 응답

```json
{
  "success": true
}
```

#### 오류 응답

- `400`: `server_ids`가 배열이 아님

### POST /api/analysis/servers/migrate

레거시 `ai_analysis` 설정에서 새 서버 레지스트리 형식으로 자동 마이그레이션합니다. 서버가 이미 존재하면 실패합니다.

#### 속도 제한

HEAVY

#### 요청

본문 불필요.

#### 응답

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `servers` | array | 마이그레이션으로 생성된 서버 |
| `migrated` | int | 생성된 서버 수 |

#### 오류 응답

- `400`: `ai_servers` 이미 존재
