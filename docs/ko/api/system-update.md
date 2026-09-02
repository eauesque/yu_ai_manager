# 시스템 업데이트 API

GitHub에서 새 버전을 확인하고 애플리케이션 업데이트를 적용하는 API입니다.
설치 방식(git / tauri / docker / portable)을 자동 감지하여 적절한 업데이트 방법을 제공합니다.

## GET /api/system/update/check

GitHub 저장소에서 새 버전이 사용 가능한지 확인합니다.

- **속도 제한**: 없음 (GET)
- **인증**: PIN 세션 또는 API Key

### 응답

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `current` | string | 현재 버전 |
| `latest` | string | GitHub의 최신 버전 |
| `update_available` | bool | 새 버전 사용 가능 여부 |
| `release_url` | string | GitHub Release 페이지 URL |
| `release_notes` | string | 릴리스 노트 (Markdown) |
| `published_at` | string | 릴리스 공개 일시 (ISO 8601) |
| `install_type` | string | 설치 방식 (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Docker 환경 전용: 업데이트 명령어 |
| `portable_download_url` | string \| null | Portable 환경 전용: 다운로드 URL |

---

## GET /api/system/update/status

현재 설치 방식과 버전 정보를 조회합니다.

- **속도 제한**: 없음 (GET)
- **인증**: PIN 세션 또는 API Key

### 응답

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `version` | string | 현재 버전 |
| `install_type` | string | 설치 방식 (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | 업데이트 진행 중 여부 |

---

## POST /api/system/update/apply

사용 가능한 업데이트를 적용합니다. git clone 및 portable 설치만 지원됩니다.

- **속도 제한**: DESTRUCTIVE
- **인증**: PIN 세션 (localhost) 또는 재시작 토큰
- **CSRF**: `X-Requested-With: XMLHttpRequest` 필수

### 요청 본문

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `confirm` | string | 예 | 확인 문자열. `"update"`를 지정 |

### 요청 예시

```json
{
  "confirm": "update"
}
```

### 응답

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE 이벤트

업데이트 중 `update.progress` 이벤트가 SSE를 통해 전달됩니다.

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `step` | string | 진행 단계 (아래 참조) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | 단계 상세 정보 |

#### 단계 목록

| 단계 | 설명 |
|------|------|
| `backup` | 백업 생성 |
| `fetch` | git fetch 실행 |
| `pull` | git pull 실행 |
| `download` | 파일 다운로드 (portable) |
| `extract` | 아카이브 추출 (portable) |
| `replace` | 파일 교체 (portable) |
| `pip_install` | Python 의존성 패키지 설치 |
| `ts_build` | TypeScript 빌드 |
| `complete` | 업데이트 완료 |

### 오류 응답

**Docker 환경** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri 환경** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## 참고 사항

- Docker 환경에서는 `/api/system/update/apply`를 사용할 수 없습니다. `docker pull`로 최신 이미지를 가져오세요
- Tauri 데스크톱 앱의 업데이트는 앱 내장 업데이터가 처리합니다
- git 및 portable 설치만 Web UI를 통한 업데이트를 지원합니다
- 업데이트 과정에서 서버가 재시작될 수 있습니다

---

## GET /api/system/update/unified-check

시스템 본체와 모든 Extension의 업데이트 상태를 일괄 확인합니다.

- **속도 제한**: 없음 (GET)
- **인증**: PIN 세션 또는 API Key

### 쿼리 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `force` | string | `"1"`로 캐시를 무시하고 재확인 |

### 응답

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `system` | object | 시스템 본체의 업데이트 정보 (`check_for_update`와 동일한 형식) |
| `extensions` | array | 각 Extension의 업데이트 상태 |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | 업데이트 가능 시 원격과의 커밋 차이 수 |
| `summary` | object | 카테고리별 집계 |

---

## POST /api/system/update/unified-apply

시스템 본체와 Extension을 일괄 업데이트합니다. 업데이트 전에 Extension 설정이 자동으로 백업됩니다.

- **속도 제한**: DESTRUCTIVE
- **인증**: PIN 세션 (localhost) 또는 재시작 토큰
- **CSRF**: `X-Requested-With: XMLHttpRequest` 필수

### 요청 본문

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `update_system` | bool | 아니오 | 시스템 본체를 업데이트할지 여부 (기본값: true) |
| `update_extensions` | bool | 아니오 | Extension을 업데이트할지 여부 (기본값: true) |
| `extension_names` | array | 아니오 | 업데이트할 Extension 이름 목록 (생략 시 모든 git Extension 대상) |

### 요청 예시

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### 응답

```json
{
  "ok": true,
  "accepted": true,
  "message": "統合更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
  "update_system": true,
  "update_extensions": true
}
```

### SSE 이벤트

통합 업데이트 중에는 `update.progress` 이벤트에 `"unified": true` 플래그가 추가됩니다.

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### 추가 단계

| 단계 | 설명 |
|------|------|
| `ext_config_backup` | Extension 설정 백업 |
| `ext_update_<name>` | 개별 Extension 업데이트 |

---

## MCP 도구 연동

Claude Desktop에서 시스템 업데이트를 관리할 수 있습니다.

```
# Step 1: 새 버전 확인
check_for_update()

# Step 2: 업데이트 상태 확인
get_update_status()

# Step 3: 업데이트 적용 (git/portable만 해당)
apply_system_update(confirm="update")

# 통합 확인: 시스템 + 모든 Extension의 업데이트를 일괄 확인
check_unified_updates()

# 통합 업데이트: 시스템 + Extension을 일괄 업데이트
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP 도구 목록

| 도구 | 설명 |
|------|------|
| `check_for_update` | GitHub에서 새 버전 사용 가능 여부 확인 |
| `get_update_status` | 현재 설치 방식과 버전 조회 |
| `apply_system_update` | 사용 가능한 업데이트 적용 (git/portable만 해당) |
| `check_unified_updates` | 시스템 + 모든 Extension의 업데이트 상태를 일괄 확인 |
| `apply_unified_updates` | 시스템 + Extension을 일괄 업데이트 (설정 자동 백업 포함) |
