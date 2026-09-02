# WD Tagger API

WD Tagger(Waifu Diffusion Tagger) Danbooru 자동 태깅 API입니다. 설정 관리, 단일/배치 태깅, 태그 CRUD, 모델 관리, XMP 읽기 및 VLM 연결 테스트 기능을 제공합니다.

## GET /api/wd-tagger/config

현재 WD Tagger 설정을 가져옵니다.

### 파라미터

없음

### 응답

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

WD Tagger 설정을 저장/업데이트합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| *(임의 키)* | any | 아니오 | 설정 필드. 알 수 없는 키나 유효하지 않은 값은 `400`을 반환 |

### 응답

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_json` | 400 | 요청 본문이 JSON 객체가 아님 |
| `invalid_value` | 400 | 유효하지 않은 설정 값 |

## POST /api/wd-tagger/tag/<file_id>

단일 파일에 대해 WD Tagger 추론을 실행하여 Danbooru 태그를 예측하고 할당합니다.

### Rate Limit

HEAVY

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `file_id` | int | 파일 ID (경로 파라미터) |

### 요청

```json
{
  "force": false
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `force` | boolean | 아니오 | `true`이면 기존 태그를 덮어쓰고 추론을 재실행. 기본값 `false` |

### 응답

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `tag_error` | 400 | 태깅 실패 (파일을 찾을 수 없음, 이미지 로드 오류 등) |

## GET /api/wd-tagger/tags/<file_id>

지정된 파일에 저장된 WD Tagger 태그를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `model` | string | 아니오 | 모델 이름으로 필터링 (쿼리 파라미터) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### 응답

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

지정된 파일의 WD Tagger 태그를 삭제합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 파일 ID (경로 파라미터) |
| `model` | string | 아니오 | 모델 이름으로 필터링 (쿼리 파라미터). 생략 시 모든 모델의 태그를 삭제 |

### 응답

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

여러 파일의 WD Tagger 태그를 일괄 삭제합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_ids` | list | 예 | 파일 ID 배열 (최대 500) |
| `model` | string | 아니오 | 모델 이름으로 필터링. 생략 시 모든 모델의 태그를 삭제 |

### 응답

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

같은 파일을 여러 WD Tagger 모델로 재태그하면 `file_wd_tags`에는 모델별 태그가
이력으로 남는다. active model을 설정하면 상세 표시, `ai_analyzed` 검색, WD Tagger
내부의 "이미 태그됨" 판정은 해당 모델의 태그만 사용한다. active model이 없으면
기존 동작처럼 모든 모델의 태그를 함께 처리한다.

### UI에서 설정

retag modal 상단에 현재 `Active model`이 표시된다. `Change` dropdown에서 사용
가능한 모델을 선택할 수 있다. `(none / reset)`을 선택하면 active model을 해제한다.

재태그가 완료되면 기본적으로 이번에 사용한 모델이 active model로 전환된다. 현재
active model을 유지하려면 retag modal의 "재태그 후 활성 모델로 설정" 체크를 끈다.

이전 모델의 row는 자동으로 물리 삭제되지 않으며, 이력 보존을 위해 DB에 남는다.
필요할 때만 retag modal에서 "다른 모델의 태그도 삭제"를 켜고 재태그 후 확인
대화상자를 승인하면 이전 모델 태그를 명시적으로 삭제한다.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

현재 active model과 DB에 존재하는 모델 목록을 반환한다. admin scope가 필요하다.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

active model을 변경한다. admin scope가 필요하다. `model_id`에 `null` 또는 빈
문자열을 보내면 active model을 해제한다.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| 코드 | 상태 | 설명 |
|------|------|------|
| `invalid_model_id` | 400 | model_id가 너무 길거나 제어 문자를 포함함 |
| `unknown_model` | 400 | 지정한 모델의 태그가 DB에 없음 |

## POST /api/wd-tagger/batch

여러 파일에 대해 배치 태깅을 실행합니다. `file_ids`를 지정하면 해당 파일만 처리합니다. 생략하면 태그가 없는 파일을 자동으로 선택하여 최대 `limit`개를 처리합니다.

### Rate Limit

HEAVY

### 요청

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| 파라미터 | 타입 | 필수 | 제한 | 설명 |
|----------|------|------|------|------|
| `file_ids` | int[] | 아니오 | 최대 500 | 대상 파일 ID 배열. 생략 시 태그 없는 파일을 자동 선택 |
| `limit` | int | 아니오 | - | `file_ids` 생략 시 최대 처리 수. 기본값 `100` |
| `force` | boolean | 아니오 | - | `true`이면 기존 태그를 덮어씀. 기본값 `false` |
| `scan_root` | string | 아니오 | - | 스캔 루트 경로로 필터링. 빈 문자열은 모든 파일 |

### 응답

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `batch_too_large` | 400 | `file_ids`가 500개를 초과 |
| `batch_error` | 409 | 배치 작업이 이미 실행 중 |

## POST /api/wd-tagger/batch/cancel

실행 중인 배치 태깅 작업을 취소합니다.

### Rate Limit

WRITE

### 요청

요청 본문이 필요 없습니다.

### 응답

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `job_not_running` | 404 | 실행 중인 배치 태깅 작업이 없음 |

## GET /api/wd-tagger/stats

WD Tagger 태깅 통계 정보를 가져옵니다.

### 파라미터

없음

### 응답

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `total_tagged` | int | 태그가 지정된 파일 수 |
| `total_tags` | int | 저장된 태그 총 수 |
| `models` | object | 모델별 태그 지정 파일 수 |
| `untagged_unknown` | int | 메타데이터 없음(`unknown`)이며 WD 태그도 없는 파일 수 |

## GET /api/wd-tagger/untagged

메타데이터 없음(`unknown`)이며 아직 태그가 지정되지 않은 파일을 나열합니다. 페이지네이션을 지원합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `limit` | int | 아니오 | 결과 수. 1-500, 기본값 `100` |
| `offset` | int | 아니오 | 건너뛸 결과 수. 기본값 `0` |

### 응답

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

지정된 파일의 XMP 메타데이터를 읽습니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `file_id` | int | 파일 ID (경로 파라미터) |

### 응답

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `file_not_found` | 404 | 파일이 존재하지 않거나 소프트 삭제됨 |

## GET /api/wd-tagger/vlm/test

VLM(Vision Language Model) 서버와의 연결을 테스트합니다. OpenAI 호환 API 엔드포인트의 도달 가능성을 확인합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `url` | string | 예 | VLM 서버 URL (쿼리 파라미터) |

### 응답

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `missing_url` | 400 | `url` 파라미터가 제공되지 않음 |
| `invalid_url` | 400 | URL 형식이 유효하지 않음 |

## GET /api/wd-tagger/vlm/models

VLM 서버에서 사용 가능한 모델을 나열합니다. OpenAI 호환 `/v1/models` 엔드포인트를 쿼리합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `url` | string | 예 | VLM 서버 URL (쿼리 파라미터) |

### 응답

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `missing_url` | 400 | `url` 파라미터가 제공되지 않음 |
| `invalid_url` | 400 | URL 형식이 유효하지 않음 |
| `vlm_connection_error` | 502 | VLM 서버에 연결할 수 없음 |

## POST /api/wd-tagger/model/download

WD Tagger 모델을 다운로드합니다. Hugging Face에서 모델 파일을 가져와 로컬에 저장합니다.

### Rate Limit

HEAVY

### 요청

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `repo` | string | 아니오 | Hugging Face 리포지토리 이름. 생략 시 설정의 `model` 값 사용 |

### 응답

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `unknown_model` | 400 | 알 수 없는 모델 리포지토리. `hint`에 알려진 모델 목록 포함 |
| `download_failed` | 500 | 다운로드 실패 |

## GET /api/wd-tagger/model/status

WD Tagger 모델의 다운로드 상태를 확인합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `repo` | string | 아니오 | Hugging Face 리포지토리 이름 (쿼리 파라미터). 생략 시 설정의 `model` 값 사용 |

### 응답

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `repo` | string | 확인 중인 리포지토리 이름 |
| `downloaded` | boolean | 모델이 로컬에 다운로드되었는지 여부 |
| `path` | string/null | 다운로드된 경우 로컬 모델 경로 |
| `known_models` | object | 지원되는 모든 모델 (리포지토리 이름 -> 표시 이름) |

## User profile CRUD (v4.197.0+)

Tools 페이지 UI에서 사용자가 만든 tagger profile을 CRUD 하기 위한 API입니다. 모든 엔드포인트는 admin scope가 필요합니다. 공통 error shape는 `{ok: false, error, code, ...extra}` 입니다. 요청 body는 **1MB hard cap** 이 있으며 (`code: profile_too_large`, 413), `id` 는 `^[a-z0-9][a-z0-9_-]{0,63}$` regex를 만족해야 합니다.

### POST /api/wd-tagger/profiles

새 user profile을 생성합니다.

**요청**: profile JSON (schema v2, `profile_version: "2"`). `builtin` 필드는 서버에서 `false` 로 강제 덮어씁니다.

**응답 (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| 필드 | 설명 |
|---|---|
| `profile` | 저장된 profile (`builtin: false` 확정) |
| `origin` | 항상 `"user"` |
| `overrides_builtin` | 같은 id의 builtin profile이 존재하면 `true` (advanced 경로) |

**에러**:

| status | code | 조건 |
|---|---|---|
| 400 | `validation_failed` | JSON이 schema v2를 위반 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | body의 `id` 가 regex 불일치 |
| 409 | `id_conflict` | 기존 user profile과 같은 id |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

지정 id의 full schema v2 profile을 가져옵니다 (UI가 편집 / 복제 / Export 시 호출).

**path**: `id` (regex check 필요)

**응답 (200)**:
{POST와 동일한 형태: profile / origin / overrides_builtin}

**에러**:
- 400 `invalid_id` (path id regex 불일치)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

기존 user profile을 업데이트합니다.

**path**: `id` (regex check 필요)

**요청**: profile JSON. `body.id` 는 path id와 반드시 일치해야 합니다 (rename은 UI에서 `Duplicate → Delete` 로 유도).

**응답 (200)**: POST와 동일한 형태.

**에러**:

| status | code | 조건 |
|---|---|---|
| 400 | `id_immutable` | path id와 body id가 불일치 |
| 400 | `invalid_id` | path id가 regex 불일치 |
| 400 | `validation_failed` | schema 위반 |
| 403 | `builtin_read_only` | path id가 builtin profile (user 측에 해당 파일 없음) |
| 404 | `not_found` | id 미등록 |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

user profile을 삭제합니다.

**path**: `id`

**응답 (200)**:
```json
{"ok": true, "deleted": true}
```

**에러**:

| status | code | 조건 |
|---|---|---|
| 400 | `invalid_id` | path id가 잘못됨 |
| 403 | `builtin_read_only` | builtin만 존재하고 user override 없음 |
| 404 | `not_found` | id 미등록 |
| 409 | `in_use` | 해당 profile이 active model ( `extra.active_model_id` 포함). UI에서 `PUT /api/wd-tagger/active-model` 로 active를 변경한 뒤 재시도하도록 안내 |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. 각 `files[]` 를 HuggingFace에 HEAD 하고, `required: true` 인 항목은 파일 단위 atomic download를 실행합니다 (캐시는 기존 경로 재사용).

**path**: `id`

**body**: 불필요

**동작**:
- per-file timeout: 30s
- 전체 timeout: 60s
- redirect: `huggingface.co` / `hf.co` 서브도메인 allowlist만 허용, 최대 5 hop, userinfo (`user:pass@`) 는 SSRFBlocked

**응답 (200, 성공)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

`status` 값:
- `downloaded`: 이번 실행에서 다운로드 완료
- `cached`: 이미 로컬에 존재 (HEAD만)
- `skipped_optional`: `required: false` 이고 404 / HEAD 실패

**에러 (status / code)**:

| status | code | 조건 |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | path id 불일치 / required 파일이 HF에서 404 |
| 404 | `not_found` | profile 미등록 |
| 408 | `timeout` | 전체 60s 초과 |
| 502 | `ssrf_blocked` | redirect가 HF allowlist 밖 / userinfo 포함 / scheme이 http(s) 아님 |
| 502 | `hf_unavailable` | HF가 5xx를 반환 |

에러 시 body는 `{"ok": false, "code": ..., "error": ..., "files": [...부분 결과...], "detail": "..."}` 형태입니다.

### profile JSON 형식 (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // HF 리포지토리 경로 "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // user 유래는 항상 false (서버가 강제)
}
```

자세한 내용은 `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), 또는 builtin 참고 구현 (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`) 을 참고하세요.
