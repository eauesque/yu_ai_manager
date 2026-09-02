# Settings API

애플리케이션 설정, 비밀 암호화 및 외부 비밀번호 관리자 통합(1Password / Bitwarden)을 관리하는 API입니다.

비밀 값은 GET 응답에서 항상 마스킹된 형태(`****`)로 반환됩니다. `source` 필드는 해당 값이 어떤 백엔드에서 해석되었는지를 나타냅니다.

## 인증

모든 엔드포인트는 PIN 인증 또는 API Key 인증이 필요합니다.

---

## GET /api/settings/schema

전체 설정 스키마 정의를 가져옵니다. 모든 설정의 키 이름, 타입, 기본값, 카테고리 및 기타 메타데이터를 반환합니다.

### 파라미터

없음

### 응답

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `key` | string | 설정 키 (점으로 구분, 예: `github.token`) |
| `type` | string | 값 타입 (`str`, `int`, `float`, `bool`) |
| `default` | any | 기본값 |
| `category` | string | 카테고리 이름 |
| `secret` | bool | 비밀 값 여부 |
| `label` | string | 표시 라벨 |

---

## GET /api/settings/all

모든 설정 값을 가져옵니다. 비밀 값은 마스킹된 형태로 반환됩니다.

### 파라미터

없음

### 응답

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `key` | string | 설정 키 |
| `value` | any | 현재 값 (비밀 값은 마스킹됨) |
| `source` | string | 값 출처: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | 비밀 값 여부 |
| `category` | string | 카테고리 이름 |

---

## GET /api/settings/\<key\>

단일 설정 값을 가져옵니다. 키는 점으로 구분된 경로 형식을 사용합니다 (예: `github.token`).

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | string | 설정 키 (경로 파라미터) |

### 응답

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 404 | `not_found` | 알 수 없는 설정 키 |

---

## PUT /api/settings/\<key\>

설정 값을 업데이트합니다. 비밀 값은 자동으로 암호화됩니다. 선택적으로 1Password URI를 지정하여 외부에서 비밀을 관리할 수 있습니다.

### Rate Limit

DESTRUCTIVE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | string | 설정 키 (경로 파라미터) |

### 요청

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `value` | any | 예 | 설정할 값. 스키마에 정의된 타입으로 자동 변환됨 |
| `op_uri` | string | 아니오 | 1Password URI. 지정 시 값 대신 `op_secrets` 매핑을 저장 |

### 응답

```json
{
  "key": "github.token",
  "updated": true
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `bad_request` | 요청 본문에 `value`가 없음 |
| 404 | `not_found` | 알 수 없는 설정 키 |

---

## GET /api/settings/secrets/status

암호화 키 백엔드 상태를 가져옵니다. 현재 사용 중인 키 관리 방식을 표시합니다.

### 파라미터

없음

### 응답

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `backend` | string | 현재 키 백엔드 (`keychain` / `passphrase` / `file`) |
| `available` | bool | 암호화 사용 가능 여부 |
| `keychain_supported` | bool | OS keychain 지원 여부 |

---

## POST /api/settings/secrets/export

암호화 키를 비밀번호로 보호된 JSON으로 내보냅니다. 백업 또는 다른 환경으로의 마이그레이션에 사용됩니다.

### Rate Limit

DESTRUCTIVE

### 요청

```json
{
  "password": "my-export-password"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `password` | string | 예 | 내보낸 데이터를 보호할 비밀번호 |

### 응답

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `bad_request` | 요청 본문에 `password`가 없음 |
| 400 | `export_failed` | 내보내기 작업 실패 |

---

## POST /api/settings/secrets/import

이전에 내보낸 데이터에서 암호화 키를 가져옵니다.

### Rate Limit

DESTRUCTIVE

### 요청

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `export_data` | string | 예 | 내보내기 시 얻은 데이터 |
| `password` | string | 예 | 내보내기 시 설정한 비밀번호 |

### 응답

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `bad_request` | `export_data` 또는 `password` 누락 |
| 400 | `import_failed` | 비밀번호 오류 또는 데이터 손상 |

---

## POST /api/settings/secrets/migrate-keychain

암호화 키를 파일 백엔드에서 OS keychain으로 마이그레이션합니다. macOS Keychain, Windows Credential Manager, Linux Secret Service를 지원합니다.

### Rate Limit

DESTRUCTIVE

### 요청

없음 (요청 본문 불필요)

### 응답

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `migration_failed` | keychain을 사용할 수 없거나 마이그레이션 실패 |

---

## GET /api/settings/op-status

1Password CLI (`op`) 연결 상태를 가져옵니다.

### 파라미터

없음

### 응답

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `available` | bool | `op` 명령이 PATH에 존재하는지 여부 |
| `signed_in` | bool | 1Password에 로그인되었는지 여부 |
| `version` | string | `op` CLI 버전 |

---

## GET /api/settings/secrets/op-vaults

사용 가능한 1Password vault를 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI를 사용할 수 없음 |

---

## POST /api/settings/secrets/push-to-op

모든 비밀 설정을 1Password에 일괄 기록하고, config.json에 `op_secrets` 매핑을 저장합니다.

### Rate Limit

DESTRUCTIVE

### 요청

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `vault` | string | 예 | 대상 1Password vault 이름 |
| `item_title` | string | 아니오 | 1Password 항목 제목. 기본값: `YU AI Manager` |
| `remove_local` | bool | 아니오 | `true`이면 푸시 후 config.json에서 로컬 암호화 값을 제거. 기본값: `false` |

### 응답

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `bad_request` | `vault` 누락 |
| 400 | `no_secrets` | 푸시할 비밀이 없음 |
| 500 | `op_push_failed` | 1Password에 기록 실패 |
| 503 | `op_unavailable` | 1Password CLI를 사용할 수 없음 |

---

## DELETE /api/settings/op-mapping/\<key\>

1Password URI 매핑을 제거하고, 로컬 암호화로 복원합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | string | 설정 키 (경로 파라미터) |

### 응답

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 404 | `not_found` | `op_secrets` 매핑에서 해당 키를 찾을 수 없음 |

---

## GET /api/settings/bw-status

Bitwarden CLI (`bw`) 연결 상태를 가져옵니다.

### 파라미터

없음

### 응답

```json
{
  "available": true,
  "status": "unlocked"
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `available` | bool | `bw` 명령이 PATH에 존재하는지 여부 |
| `status` | string | Bitwarden 세션 상태 |

---

## GET /api/settings/secrets/bw-folders

사용 가능한 Bitwarden 폴더를 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI를 사용할 수 없음 |

---

## POST /api/settings/secrets/push-to-bw

모든 비밀 설정을 Bitwarden에 일괄 기록하고, config.json에 `bw_secrets` 매핑을 저장합니다.

### Rate Limit

WRITE

### 요청

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `folder_id` | string/null | 아니오 | 대상 Bitwarden 폴더 ID. 생략 시 폴더를 지정하지 않음 |
| `item_name` | string | 아니오 | Bitwarden 항목 이름. 기본값: `YU AI Manager` |

### 응답

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 400 | `no_secrets` | 푸시할 비밀이 없음 |
| 500 | `bw_push_failed` | Bitwarden에 기록 실패 |
| 503 | `bw_unavailable` | Bitwarden CLI를 사용할 수 없음 |

---

## DELETE /api/settings/bw-mapping/\<key\>

Bitwarden 매핑을 제거하고, 로컬 암호화로 복원합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `key` | string | 설정 키 (경로 파라미터) |

### 응답

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 에러

| 상태 코드 | 코드 | 설명 |
|--------|------|-------------|
| 404 | `not_found` | `bw_secrets` 매핑에서 해당 키를 찾을 수 없음 |
