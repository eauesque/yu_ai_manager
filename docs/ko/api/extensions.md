# Extensions API

Extension의 설치, 보안, 개발을 관리하는 API입니다.

---

## GET /api/extensions

설치된 모든 Extension을 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `extensions` | array | Extension 정보 배열 |
| `total` | int | Extension 총 수 |
| `category_order` | string[] | 카테고리 표시 순서 |

## GET /api/extensions/\<name\>

특정 Extension의 상세 정보를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### 에러

- `404` — Extension을 찾을 수 없음

## POST /api/extensions/\<name\>/toggle

Extension의 활성화/비활성화 상태를 전환합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 요청

```json
{
  "enabled": true
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `enabled` | boolean | 아니오 | `true`로 활성화, `false`로 비활성화. 생략 시 현재 상태를 토글(반전) |

### 응답

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### 에러

- `404` — Extension을 찾을 수 없음

## GET /api/extensions/\<name\>/config

Extension의 설정 스키마와 현재 값을 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### 에러

- `404` — Extension을 찾을 수 없음

## POST /api/extensions/\<name\>/config

Extension 설정값을 저장합니다. 유효성 검사를 포함합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 요청

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `values` | object | 예 | 필드 키와 값의 매핑 |

### 응답

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### 에러

- `404` — Extension을 찾을 수 없음
- `400` — 유효성 검사 에러

---

## Extension 설치 / 업데이트 / 제거

다음 엔드포인트는 **localhost 접근만 허용**됩니다. 원격 요청은 `403`을 반환합니다.

## POST /api/extensions/install

Git 저장소에서 Extension을 설치합니다.

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 요청

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `url` | string | 예 | Git 저장소 URL. `git`과 `repo`를 별칭으로 사용 가능 |

### 응답

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### 에러

- `400` — URL이 제공되지 않았거나 URL 형식이 잘못됨
- `403` — localhost가 아닌 접근

## POST /api/extensions/\<name\>/update

특정 Extension을 최신 버전으로 업데이트합니다 (git pull).

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### 에러

- `403` — localhost가 아닌 접근
- `404` — Extension을 찾을 수 없음

## POST /api/extensions/update-all

Git으로 설치된 모든 Extension을 일괄 업데이트합니다.

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 응답

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### 에러

- `403` — localhost가 아닌 접근

## DELETE /api/extensions/\<name\>/uninstall

Extension을 제거합니다 (디렉토리 삭제).

### Rate Limit

DESTRUCTIVE

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### 에러

- `403` — localhost가 아닌 접근
- `404` — Extension을 찾을 수 없음

---

## 보안 및 권한

## GET /api/extensions/\<name\>/permissions

Extension의 권한 정보와 승인 상태를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `trust_level` | string | 신뢰 수준 (`trusted`, `L1`, `L2`) |
| `approved` | boolean | 사용자가 이 Extension을 승인했는지 여부 |
| `permissions.required` | array | 필수 권한 목록 |
| `permissions.optional` | array | 선택적 권한 목록 |
| `granted` | object/null | 부여된 권한의 상세 정보. 미승인 시 `null` |

### 에러

- `404` — Extension을 찾을 수 없음

## POST /api/extensions/\<name\>/permissions

Extension 권한을 승인하거나 철회합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 요청 (승인)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 요청 (철회)

```json
{
  "action": "revoke"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `action` | string | 아니오 | `"approve"` (기본값) 또는 `"revoke"` |
| `granted` | string[] | 아니오 | 부여할 권한 이름 목록 (승인 시) |
| `denied` | string[] | 아니오 | 거부할 권한 이름 목록 (승인 시) |

### 응답 (승인)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 응답 (철회)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### 에러

- `400` — `granted`가 목록이 아님
- `404` — Extension을 찾을 수 없음

## GET /api/extensions/\<name\>/scan-results

Extension 코드의 정적 분석 결과를 가져옵니다. ManifestAuthority와 CodeVerifier 결과를 모두 반환합니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `manifest_review.approved` | boolean | manifest가 심사를 통과했는지 여부 |
| `manifest_review.issues` | array | 문제 목록 (`severity`, `message`) |
| `code_scan` | object/null | 코드 스캔 결과. 디렉토리가 없으면 `null` |
| `code_scan.findings` | array | 발견 사항 목록 |

### 에러

- `404` — Extension을 찾을 수 없음

## POST /api/extensions/\<name\>/rescan

Extension 코드를 재스캔합니다. `scan-results`와 동일한 형식을 반환합니다.

### Rate Limit

WRITE

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

`GET /api/extensions/<name>/scan-results`와 동일한 형식입니다.

## GET /api/extensions/\<name\>/tokens

Extension의 capability token 발급 상태를 가져옵니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### 에러

- `404` — Extension을 찾을 수 없음

## GET /api/extensions/\<name\>/integrity

Extension의 파일 무결성 상태를 가져옵니다. revocation tracker 및 import guard 정보도 포함됩니다.

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `integrity` | object | 파일 무결성 검사 결과 |
| `revocation` | object | Token revocation tracker 정보 |
| `import_guard` | object | Import guard 거부 횟수 |

### 에러

- `404` — Extension을 찾을 수 없음

---

## Hook 및 Marketplace

## GET /api/extensions/hooks

등록된 Extension hook 및 hook 정의를 나열합니다.

### 파라미터

없음

### 응답

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `hooks` | object | hook 이름과 등록된 Extension 목록의 매핑 |
| `definitions` | object | 사용 가능한 hook 정의. `mode`는 실행 모드 |

## GET /api/extensions/marketplace

Marketplace Extension을 검색합니다.

### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `q` | string | 아니오 | 검색 쿼리 (쿼리 파라미터). 빈 문자열이면 전체 반환 |

### 응답

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `extensions` | array | Marketplace Extension 정보 |
| `extensions[].installed` | boolean | 로컬에 설치되었는지 여부 |
| `total` | int | 검색 결과 총 수 |

## POST /api/extensions/marketplace/refresh

Marketplace 캐시를 강제로 새로고침합니다.

### Rate Limit

WRITE

### 응답

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## 격리

## GET /api/extensions/isolation

프로세스 격리 상태를 가져옵니다.

### 파라미터

없음

### 응답

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `available` | boolean | 프로세스 격리 사용 가능 여부 |
| `processes` | object | Extension 이름과 프로세스 상태의 매핑 |

## GET /api/extensions/os-isolation

OS 수준의 격리 상태를 가져옵니다 (Phase D). 프로세스 격리 정보도 포함됩니다.

### 파라미터

없음

### 응답

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `os_isolation` | object | OS 수준 격리 정보 |
| `config.enabled` | boolean | OS 격리 활성화 여부 |
| `config.apparmor` | boolean | AppArmor (Linux) 사용 상태 |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec 사용 상태 |
| `config.macos_user_isolation` | boolean | macOS 사용자 격리 사용 상태 |
| `config.windows_restricted_token` | boolean | Windows restricted token 사용 상태 |
| `config.windows_job_object` | boolean | Windows Job Object 사용 상태 |
| `processes` | object | 프로세스 격리 상태 |

---

## Extension 개발

커스텀 Extension을 생성하고 편집하는 API입니다. concession 모델 기반으로, `extensions/custom-{name}/` 디렉토리만 쓰기가 가능합니다.

모든 엔드포인트는 **localhost 접근만 허용**됩니다.

### 보안 제약

- Extension 이름: 소문자 영숫자와 하이픈만 허용 (`[a-z0-9-]`), 최대 50자, `builtin-` 접두사 사용 금지
- 파일 유형: 화이트리스트만 허용 (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- 바이너리 파일: 완전 금지
- 파일 크기 제한: 유형에 따라 10KB~50KB

## POST /api/extensions/author/create

새로운 커스텀 Extension을 생성하고 스캐폴드 파일을 만듭니다.

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 요청

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `name` | string | 예 | Extension 이름 (`[a-z0-9-]`, 최대 50자) |
| `description` | string | 아니오 | Extension 설명 |

### 응답

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### 에러

- `400` — 잘못된 이름이거나 Extension이 이미 존재함
- `403` — localhost가 아닌 접근

## POST /api/extensions/author/\<name\>/write

커스텀 Extension에 파일을 작성합니다.

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터, `custom-` 접두사 제외) |

### 요청

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `file_type` | string | 예 | 파일 유형. `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` 중 하나 |
| `filename` | string | 예 | 확장자를 제외한 파일 이름. 영숫자, 하이픈, 밑줄만 허용 |
| `content` | string | 예 | 파일 내용 (텍스트만 허용) |

### 파일 유형 제약

| file_type | 확장자 | 최대 크기 | 비고 |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Extension 진입점 |
| `template` | `.html` | 50KB | `templates/{name}/`에 배치 |
| `static_css` | `.css` | 50KB | `static/`에 배치 |
| `static_js` | `.js` | 50KB | `static/`에 배치 |
| `config` | `.json` | 10KB | 파일 이름은 `extension`이어야 함 |
| `readme` | `.md` | 20KB | 파일 이름은 `README`여야 함 |

### 응답

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### 에러

- `400` — 유효성 검사 에러 (잘못된 이름, 파일 유형, 크기 초과, 바이너리 감지)
- `403` — localhost가 아닌 접근

## GET /api/extensions/author/\<name\>/read

커스텀 Extension의 파일을 읽습니다.

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 쿼리 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|-----------|------|----------|-------------|
| `file_type` | string | 예 | 파일 유형 |
| `filename` | string | 예 | 확장자를 제외한 파일 이름 |

### 응답

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### 에러

- `400` — 유효성 검사 에러
- `403` — localhost가 아닌 접근

## GET /api/extensions/author/\<name\>/files

커스텀 Extension의 모든 파일을 나열합니다.

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### 에러

- `400` — 잘못된 Extension 이름
- `403` — localhost가 아닌 접근

## POST /api/extensions/author/\<name\>/validate

커스텀 Extension의 extension.json과 코드를 검증합니다. Extension을 등록하지 않고 CodeVerifier를 실행합니다.

### Rate Limit

WRITE

### 접근 제한

localhost만 허용

### 파라미터

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `name` | string | Extension 이름 (경로 파라미터) |

### 응답 (성공)

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### 응답 (문제 발견)

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `ok` | boolean | 모든 검사를 통과했는지 여부 |
| `issues` | string[] | manifest 및 코드 검증 문제 |
| `code_findings` | array | CodeVerifier 발견 사항 |
| `manifest` | object | 파싱된 extension.json 내용 |

### 에러

- `400` — 잘못된 Extension 이름이거나 Extension이 존재하지 않음
- `403` — localhost가 아닌 접근
