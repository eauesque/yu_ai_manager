# API Keys API

API Key의 생성, 목록 조회, 삭제를 위한 API입니다. 모든 엔드포인트에 PIN 세션 인증이 필요합니다.

API Key는 `sk_` + 32자리 16진수 문자(128비트) 형식으로 생성됩니다. 서버 측에는 해시값만 저장되며, 원본 키는 생성 시에만 한 번 반환됩니다.

## Scopes

API Key에 scope를 지정하여 접근 가능한 엔드포인트를 제한할 수 있습니다. scope가 지정되지 않은 키는 기본적으로 읽기 전용 접근 권한을 갖습니다.

| Scope | 설명 |
|-------|------|
| `read` | 검색, 파일 상세정보, 썸네일, 통계 |
| `rate` | 평점 조회/설정/일괄 처리 |
| `tag.write` | 태그 추가/삭제 |
| `collection.write` | 컬렉션 생성/수정/삭제, 일괄 추가, 즐겨찾기 |
| `annotate` | 주석 읽기/쓰기/삭제 |
| `scan` | 스캔 시작/취소/재개 |
| `admin` | API Key 관리, 설정, 백업/복원 |

## POST /api/apikeys

새 API Key를 생성합니다.

### Rate Limit

WRITE (scope: `admin`)

### Authentication

PIN 세션 또는 `admin` scope를 가진 API Key

### Request

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `label` | string | 아니오 | 키의 식별 라벨. 생략 시 `Key <timestamp>`가 기본값 |
| `scopes` | string[] | 아니오 | Scope 배열. 생략하거나 빈 배열을 전달하면 읽기 전용 접근 |

### Response (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **참고**: `key` 필드는 생성 응답에서만 포함됩니다. 이 값은 다시 조회할 수 없으므로 안전한 장소에 보관하세요.

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 유효하지 않은 scope 지정 |

## GET /api/apikeys

모든 API Key를 목록으로 조회합니다. 해시값은 포함되지 않으며, 접두사만 반환됩니다.

### Authentication

PIN 세션 또는 `admin` scope를 가진 API Key

### Parameters

없음

### Response

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | Key ID (`ak_` 접두사) |
| `key_prefix` | string | 키의 처음 10자 (식별용) |
| `label` | string | 사용자 정의 라벨 |
| `created_at` | int | 생성 시간 (Unix 타임스탬프) |
| `last_used_at` | int/null | 마지막 사용 시간. 사용한 적 없으면 `null` |
| `scopes` | string[] | 지정된 scope. scope가 설정되지 않은 경우 이 필드 생략 |

## DELETE /api/apikeys/<key_id>

API Key를 삭제(폐기)합니다.

### Rate Limit

WRITE (scope: `admin`)

### Authentication

PIN 세션 또는 `admin` scope를 가진 API Key

### Parameters

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `key_id` | string | API Key ID (경로 매개변수) |

### Response

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errors

| 상태 코드 | 설명 |
|-----------|------|
| 404 | 지정된 ID의 키를 찾을 수 없음 |

## API Key 사용 방법

생성된 API Key를 `Authorization` 헤더를 통해 사용합니다:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

API Key로 인증된 요청에는 CSRF 헤더(`X-Requested-With`)가 필요하지 않습니다.
