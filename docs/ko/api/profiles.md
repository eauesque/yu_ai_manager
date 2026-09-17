# Profiles API

설정 프로필 관리 API입니다. Profile은 애플리케이션 설정의 명명된 스냅샷으로, `profiles/<name>.json`으로 저장됩니다.

모든 엔드포인트는 PIN 인증이 필요합니다. PIN 인증이 비활성화되면 403을 반환하고, 세션이 인증되지 않으면 401을 반환합니다.

## Profile 이름 규칙

- 1~64자
- 허용 문자: `a-zA-Z0-9_-`

---

## GET /api/profiles

모든 Profile의 메타데이터를 나열합니다. 즐겨찾기 우선으로 정렬한 후 라벨 알파벳순으로 정렬됩니다.

### 파라미터

없음

### 응답

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | Profile 이름 (파일명으로 사용) |
| `label` | string | 표시 라벨 |
| `description` | string | 설명 텍스트 |
| `favorite` | boolean | 즐겨찾기 플래그 |
| `last_used_at` | string/null | 마지막 사용 타임스탬프 (ISO 8601) |
| `created_at` | string/null | 생성 타임스탬프 (ISO 8601) |
| `db` | string/null | 연결된 데이터베이스 경로 |
| `is_active` | boolean | 현재 활성 Profile 여부 |

## GET /api/profiles/\<name\>

지정된 Profile의 전체 데이터를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | Profile 이름 (경로 파라미터) |

### 응답

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_profile_name` | 400 | Profile 이름 무효 |
| `profile_not_found` | 404 | Profile이 존재하지 않음 |

## POST /api/profiles

새 Profile을 생성합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `name` | string | 예 | Profile 이름 (`a-zA-Z0-9_-`, 1-64자) |
| `label` | string | 아니오 | 표시 라벨. 생략 시 `name`이 기본값 |
| `description` | string | 아니오 | 설명 텍스트 |
| `base_config` | object | 아니오 | 초기 설정 값. 메타데이터 키 (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) 이외의 키가 Profile에 복사됨 |

### 응답 (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_profile_name` | 400 | Profile 이름 무효 |
| `invalid_label` | 400 | 라벨이 비어 있음 |
| `profile_exists` | 409 | 동일한 이름의 Profile이 이미 존재 |

## PUT /api/profiles/\<name\>

Profile 메타데이터를 업데이트합니다. `label`, `description`, `favorite`만 변경할 수 있습니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | Profile 이름 (경로 파라미터) |

### 요청

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `label` | string | 아니오 | 표시 라벨 |
| `description` | string | 아니오 | 설명 텍스트 |
| `favorite` | boolean | 아니오 | 즐겨찾기 플래그 |

최소 하나의 필드가 필요합니다.

### 응답

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `empty_update` | 400 | 업데이트할 필드가 지정되지 않음 |
| `update_failed` | 400 | Profile을 찾을 수 없음 등 |

## DELETE /api/profiles/\<name\>

Profile을 삭제합니다. 현재 활성 Profile은 삭제할 수 없습니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | Profile 이름 (경로 파라미터) |

### 응답

```json
{
  "deleted": "my_profile"
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `delete_active` | 400 | 활성 Profile은 삭제할 수 없음 |
| `delete_failed` | 400 | Profile을 찾을 수 없음 등 |

## POST /api/profiles/\<name\>/duplicate

새 이름으로 Profile을 복제합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | 원본 Profile 이름 (경로 파라미터) |

### 요청

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `new_name` | string | 예 | 새 Profile 이름 |
| `new_label` | string | 아니오 | 새 표시 라벨. 생략 시 `new_name`이 기본값 |

### 응답 (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `duplicate_failed` | 400 | 원본을 찾을 수 없거나, 새 이름이 무효하거나, 이름이 이미 존재 |

## POST /api/profiles/\<name\>/rename

Profile의 이름을 변경합니다. 활성 Profile의 이름이 변경되면 `config.json`의 `active_profile`이 자동으로 업데이트됩니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | 현재 Profile 이름 (경로 파라미터) |

### 요청

```json
{
  "new_name": "renamed_profile"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `new_name` | string | 예 | 새 Profile 이름 |

### 응답

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_profile_name` | 400 | 새 Profile 이름 무효 |
| `rename_failed` | 400 | 원본 Profile을 찾을 수 없거나 새 이름이 이미 존재 |

## POST /api/profiles/\<name\>/favorite

Profile의 즐겨찾기 상태를 토글합니다. 현재 `favorite` 값을 반전시킵니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | Profile 이름 (경로 파라미터) |

### 요청

요청 본문이 필요 없습니다.

### 응답

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `profile_not_found` | 404 | Profile이 존재하지 않음 |
| `favorite_failed` | 400 | 업데이트 실패 |

---

## QR 내보내기 / 가져오기

Profile을 QR 코드용 JSON 문자열로 내보내거나 QR 코드에서 Profile을 가져옵니다. 내보내기 시 `pin`, `token`, `secret`, `key`를 포함하는 민감한 필드는 자동으로 제거됩니다.

## GET /api/profiles/\<name\>/export

Profile을 QR 코드용 JSON 문자열로 내보냅니다. 민감한 필드는 제외됩니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `name` | string | Profile 이름 (경로 파라미터) |

### 응답

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data`는 QR 코드에 삽입하기 위한 JSON 문자열입니다. `schema` 필드는 형식 버전을 식별합니다.

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `profile_not_found` | 404 | Profile이 존재하지 않음 |

## POST /api/profiles/import-preview

QR 데이터의 가져오기를 미리 봅니다. 기존 Profile과의 차이를 확인하는 데 사용됩니다. 실제 가져오기는 수행되지 않습니다.

### Rate Limit

WRITE

### 요청

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `qr_data` | string/object | 예 | QR 코드의 JSON 문자열 또는 파싱된 객체 |

### 응답 (새 Profile)

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### 응답 (기존 Profile)

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_qr` | 400 | 유효하지 않은 QR 데이터 또는 `profile` 키 누락 |
| `invalid_profile_name` | 400 | Profile 이름 무효 |

## POST /api/profiles/import

QR 데이터에서 Profile을 가져옵니다. 세 가지 모드를 지원합니다: 새로 생성, 차이 병합, 전체 덮어쓰기.

### Rate Limit

WRITE

### 요청

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `qr_data` | string/object | 예 | QR 코드의 JSON 문자열 또는 파싱된 객체 |
| `mode` | string | 아니오 | 가져오기 모드: `full` (전체 덮어쓰기, 기본값), `diff` (변경된 키만 병합), `new` (새로 생성만) |

### 응답

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

새 Profile을 생성할 때 상태 코드 201을 반환합니다.

### 오류

| 코드 | 상태 코드 | 설명 |
|------|-----------|------|
| `invalid_qr` | 400 | 유효하지 않은 QR 데이터 |
| `invalid_profile_name` | 400 | Profile 이름 무효 |
| `profile_exists` | 409 | `mode=new`일 때 Profile이 이미 존재 |
| `import_failed` | 400 | 가져오기 실패 |
