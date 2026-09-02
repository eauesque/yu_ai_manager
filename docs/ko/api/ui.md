# UI Management API

UI 테마의 목록 조회, 전환, 설치, 제거를 위한 API입니다.

## GET /api/ui/list

설치된 모든 UI를 목록으로 조회합니다. 각 UI의 manifest 정보, 활성화 상태, 템플릿/정적 파일 존재 여부를 반환합니다.

### Parameters

없음

### Response

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | UI 디렉터리 이름 |
| `active` | boolean | 현재 활성화된 UI인지 여부 |
| `manifest` | object | `manifest.json`의 내용 |
| `has_templates` | boolean | `templates/` 디렉터리 존재 여부 |
| `has_static` | boolean | `static/` 디렉터리 존재 여부 |

## POST /api/ui/switch

활성 UI를 전환합니다. 변경 사항은 `config.json`에 저장되며, 서버를 재시작해야 적용됩니다.

### Rate Limit

WRITE

### Request

```json
{
  "name": "custom-dark"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `name` | string | 예 | 대상 UI 이름. 영숫자, 하이픈, 밑줄만 허용 |

### Response

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errors

| 상태 코드 | 조건 |
|-----------|------|
| 400 | UI 이름이 비어 있거나 유효하지 않은 문자 포함 |
| 404 | 지정된 UI가 존재하지 않음 |
| 400 | `manifest.json`이 없거나 유효하지 않음 |
| 500 | `config.json` 저장 실패 |

## POST /api/ui/install

URL에서 UI를 설치합니다. **localhost에서만 허용됩니다.**

### Rate Limit

WRITE

### Authentication

PIN 또는 API Key 인증이 필요하며, 요청은 localhost에서 발생해야 합니다. 원격 요청은 403으로 거부됩니다.

### Request

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| 매개변수 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `url` | string | 예 | UI 패키지의 URL (zip 아카이브 등) |

### Response

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errors

| 상태 코드 | 조건 |
|-----------|------|
| 400 | URL이 비어 있음 |
| 403 | localhost가 아닌 곳에서의 요청 |

## DELETE /api/ui/<name>/uninstall

UI를 제거합니다. **localhost에서만 허용됩니다.** 기본 UI(`default`)는 제거할 수 없습니다.

제거된 UI가 현재 활성화 상태인 경우, `config.json`의 UI 설정이 초기화되고 기본 UI가 복원됩니다.

### Rate Limit

WRITE

### Authentication

PIN 또는 API Key 인증이 필요하며, 요청은 localhost에서 발생해야 합니다. 원격 요청은 403으로 거부됩니다.

### Parameters

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `name` | string | UI 이름 (경로 매개변수). 영숫자, 하이픈, 밑줄만 허용 |

### Response

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errors

| 상태 코드 | 조건 |
|-----------|------|
| 400 | 유효하지 않은 UI 이름이거나 `default` 제거 시도 |
| 403 | localhost가 아닌 곳에서의 요청 |
| 404 | 지정된 UI가 존재하지 않음 |
