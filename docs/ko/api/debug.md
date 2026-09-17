# Debug API

디버깅 및 진단을 위한 내부 API입니다. 파일 메타데이터 검사, 모델 정보 확인, 스캔된 루트 디렉터리 관리에 사용됩니다.

이 엔드포인트들은 프론트엔드 UI가 없으며 주로 개발 및 문제 해결 용도입니다.

## GET /api/debug/file-meta/<file_id>

파일의 상세 메타데이터를 검사합니다. 데이터베이스에 저장된 메타데이터를 반환하며, ZIP 아카이브 내의 파일인 경우 새로 추출한 결과도 함께 반환합니다.

### Authentication

PIN 세션 또는 API Key

### Parameters

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `file_id` | int | 파일 ID (경로 매개변수) |

### Response

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | int | 파일 ID |
| `path` | string | 파일 경로 |
| `meta_source` | string | 메타데이터 출처 (`a1111_png`, `novelai_v4_png` 등) |
| `parser_version` | int | 파서 버전 |
| `format` | string | 템플릿 형식 |
| `model_name` | string/null | 모델 이름 |
| `raw_prompt_length` | int | 원본 프롬프트 문자 수 |
| `raw_prompt_preview` | string | 원본 프롬프트의 처음 300자 |
| `raw_negative_preview` | string | 네거티브 프롬프트의 처음 300자 |
| `raw_meta_json_length` | int | 원본 메타데이터 JSON 문자 수 |
| `raw_meta_json_preview` | string | 원본 메타데이터 JSON의 처음 500자 |
| `has_v4_prompt` | bool | NovelAI V4 프롬프트 포함 여부 |
| `has_comment` | bool | Comment 필드 포함 여부 |

ZIP 아카이브 내의 파일인 경우, 재추출 결과가 포함된 `fresh_extract` 필드가 추가됩니다:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 404 | 파일을 찾을 수 없음 |

## GET /api/debug/model-check

templates 테이블에서 `model_name`의 저장 상태를 확인합니다. 모델 이름이 있는 레코드와 없는 레코드의 통계 및 샘플을 반환합니다.

### Authentication

PIN 세션 또는 API Key

### Parameters

없음

### Response

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `total_templates` | int | 전체 템플릿 수 |
| `with_model_name` | int | 모델 이름이 설정된 레코드 수 |
| `without_model_name` | int | 모델 이름이 없는 레코드 수 |
| `samples_with_model` | array | 모델 이름이 있는 샘플 (최대 10개) |
| `samples_without_model` | array | 모델 이름이 없는 샘플 (최대 5개) |

## GET /api/scanned-roots

데이터베이스에 등록된 파일에서 루트 디렉터리를 추출하여 파일 수와 함께 반환합니다. 구성된 스캔 루트 디렉터리와 어떤 구성된 루트에도 속하지 않는 파일의 루트 디렉터리를 모두 집계합니다.

### Authentication

PIN 세션 또는 API Key

### Parameters

없음

### Response

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `roots` | array | 루트 디렉터리 배열 (파일 수 내림차순 정렬, 최대 50개) |
| `roots[].path` | string | 디렉터리 경로 |
| `roots[].count` | int | 해당 경로 하위의 파일 수 |

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 500 | 루트 디렉터리 요약을 계산할 수 없음 |

## POST /api/debug/query

읽기 전용 SQL 쿼리를 실행합니다. `YU_DEBUG_MODE=1` 환경 변수가 필요하며 localhost에서만 접근할 수 있습니다.

### Rate Limit

WRITE

### Authentication

PIN 세션 또는 API Key (localhost 전용 + `YU_DEBUG_MODE=1`)

### Request

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `sql` | string | 예 | 실행할 SELECT 문 |
| `limit` | int | 아니오 | 반환할 최대 행 수 (기본값: 100, 최대: 10000) |

### 제약 조건

- SELECT 문만 허용됩니다 (INSERT, UPDATE, DELETE 등은 거부됨)
- 여러 문장 (세미콜론으로 구분된 다중 쿼리)은 허용되지 않습니다
- 쓰기 키워드 (DROP, ALTER, CREATE 등)가 포함된 쿼리는 거부됩니다

### Response

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `columns` | string[] | 컬럼명 배열 |
| `rows` | object[] | 결과 행 (각 행은 컬럼명을 키로 하는 객체) |
| `row_count` | int | 반환된 행 수 |
| `truncated` | bool | limit에 의해 결과가 잘린 경우 `true` |

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 400 | SQL이 비어 있음, 여러 문장, SELECT가 아닌 쿼리, 쓰기 작업 포함, SQL 구문 오류 |
| 403 | Debug 모드가 활성화되지 않았거나 localhost가 아닌 곳에서 접근 |

## POST /api/scanned-roots/purge

지정된 경로 하위의 모든 파일 레코드를 데이터베이스에서 영구 삭제합니다. 관련 레코드 (태그, 템플릿 등)는 캐스케이드 삭제됩니다. 사용하지 않는 태그는 자동으로 정리됩니다.

### Rate Limit

DESTRUCTIVE

### Authentication

PIN 세션 또는 API Key

### Request

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `path` | string | 예 | 삭제할 루트 경로. 이 경로 하위의 모든 파일이 삭제됩니다 |

### Response

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `purged` | int | 삭제된 파일 레코드 수 |
| `path` | string | 지정된 경로 |

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 경로가 지정되지 않음 |
| 500 | 삭제 작업 실패 |
