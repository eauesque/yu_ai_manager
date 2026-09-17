# Tools API

중복 감지, 해시 계산, 유사 이미지 검색, 캐시 관리, 폴더 선택, DB 백업, 아카이브 정리 및 디버그 로그를 위한 유틸리티 API입니다.

---

## 중복 / 해시 / 스캔

### GET /api/tools/find-duplicates

파일 해시 또는 파일명을 기반으로 중복 파일을 감지합니다.

#### Rate Limit

HEAVY

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `cross_directory` | string | `"false"` | `"true"`로 설정하면 다른 디렉토리 간 중복을 감지 |
| `method` | string | `"hash"` | 감지 방법: `"hash"` 또는 `"name"` |
| `threshold` | int | `5` | 유사도 임계값 |

#### 응답

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

해시가 없는 파일에 대해 백그라운드 해시 계산을 시작합니다.

#### Rate Limit

HEAVY

#### 요청

```json
{
  "type": "both",
  "limit": 5000
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `type` | string | `"both"` | 해시 유형: `"md5"`, `"sha256"` 또는 `"both"` |
| `limit` | int | `5000` | 최대 처리 파일 수 |

#### 응답

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

중복 그룹에서 지정된 파일을 삭제합니다.

#### Rate Limit

DESTRUCTIVE

#### 요청

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `groups` | array | 필수 | 삭제 대상. `keep` = 보존할 파일 ID, `delete` = 제거할 파일 ID 배열 |
| `mode` | string | `"soft"` | `"soft"` = 논리 삭제, `"hard"` = 물리 삭제 |

#### 응답

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

태그를 정규화합니다 (중복 병합, 공백 제거 등).

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `dry_run` | string | `"false"` | `"true"`로 설정하면 실제 적용 없이 변경 사항을 미리 봄 |

#### 응답

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

지정된 파일과 유사한 이미지를 검색합니다 (해시 기반).

#### Rate Limit

HEAVY

#### 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `file_id` | int | 예 | 참조 파일 ID |
| `threshold` | int | 아니오 | 유사도 임계값 (1-20, 기본값 `5`) |

#### 응답

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### 오류

- `400` — `file_id` 누락 또는 무효
- `404` — 지정된 파일을 찾을 수 없음

### POST /api/tools/scan

디렉토리의 파일을 스캔하여 데이터베이스에 등록합니다.

#### Rate Limit

HEAVY

#### 요청

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `path` | string | 필수 | 스캔할 디렉토리 경로 |
| `recursive` | bool | `true` | 하위 디렉토리를 재귀적으로 스캔 |
| `scan_zips` | bool | `false` | ZIP 아카이브 내부도 스캔 |
| `compute_hash` | bool | `false` | 스캔 중 파일 해시 계산 |

#### 응답

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## 파일 검색 / 메타데이터 검사

### GET /api/tools/file-search

키워드로 데이터베이스의 파일을 검색합니다.

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `q` / `query` | string | `""` | 검색 키워드 |
| `meta` / `meta_filter` | string | `"all"` | 메타데이터 소스별 필터 (`"all"`, `"a1111_png"`, `"novelai_v4_png"` 등) |
| `limit` / `n` / `page_size` | int | `100` | 결과 수 (1-500) |

#### 응답

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

업로드된 파일의 메타데이터를 검사합니다. 데이터베이스에 파일을 등록하지 않고 메타데이터만 추출합니다.

#### Rate Limit

WRITE

#### 요청

`multipart/form-data`:

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file` | file | 예 | 검사할 파일 |
| `zip_entry` | string | 아니오 | ZIP 아카이브 내 경로 (ZIP 파일용) |

#### 응답

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### 오류

- `400` — 파일이 업로드되지 않음

---

## 폴더 선택 / 디렉토리 목록

### GET /api/tools/select-folder

OS 네이티브 폴더 선택 대화상자를 엽니다. **localhost에서만 사용 가능합니다.**

#### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `initial` / `path` / `dir` | string | 대화상자의 초기 디렉토리 |

#### 응답

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

원격 접속 시:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

서버의 디렉토리를 나열합니다. **localhost에서만 사용 가능합니다.**

#### 파라미터

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `path` / `dir` / `initial` | string | 나열할 디렉토리. 비워두면 루트 디렉토리를 반환 |

#### 응답

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### 오류

- `403` — 원격 접속

---

## 캐시 관리

### GET /api/tools/cache-info

썸네일 캐시 상태를 가져옵니다.

#### 응답

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

모든 썸네일 캐시를 삭제합니다.

#### Rate Limit

DESTRUCTIVE

#### 응답

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

그룹 인덱스 캐시를 강제로 재구축합니다.

#### Rate Limit

DESTRUCTIVE

#### 응답

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

백그라운드에서 모든 MP4/MOV 파일의 faststart 캐시를 사전 생성합니다. 즉시 202를 반환합니다.

#### Rate Limit

WRITE

#### 응답 (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

이미 실행 중일 때 (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## 설정

### GET /api/settings/config

기본값과 병합된 현재 설정을 가져옵니다.

#### 응답

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

설정을 부분 업데이트합니다. 기존 중첩 객체에 대해 딥 머지가 적용됩니다.

#### Rate Limit

DESTRUCTIVE

#### 요청

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### 응답

```json
{
  "status": "saved"
}
```

#### 오류

- `400` — 빈 데이터

---

## 데이터베이스 백업 / 복원

### GET /api/tools/backup-download

데이터베이스 파일을 직접 다운로드합니다. **localhost에서만 사용 가능합니다.**

#### 응답

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- 데이터베이스를 찾을 수 없으면 404 반환

### POST /api/tools/restore

`.db` 파일을 업로드하여 데이터베이스를 복원합니다. **localhost에서만 사용 가능합니다.** 복원 전에 기존 데이터베이스의 백업이 자동으로 생성됩니다.

#### Rate Limit

WRITE

#### 요청

`multipart/form-data`:

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file` | file | 예 | 확장자가 `.db`인 SQLite 파일 |

#### 유효성 검사

- SQLite magic bytes 확인
- `files` 테이블 존재 확인
- trigger 또는 view가 포함된 데이터베이스는 거부

#### 응답

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### 오류

- `400` — 파일 미업로드, 확장자 오류 또는 유효하지 않은 SQLite
- `403` — 원격 접속
- `500` — 백업 또는 복원 실패

### POST /api/tools/backup/create

관리 백업을 수동으로 생성합니다. **localhost에서만 사용 가능합니다.**

#### Rate Limit

DESTRUCTIVE

#### 응답

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

사용 가능한 백업을 나열합니다.

#### 응답

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

지정된 백업에서 데이터베이스를 복원합니다. **localhost에서만 사용 가능합니다.**

#### Rate Limit

DESTRUCTIVE

#### 요청

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `filename` | string | 예 | 복원할 백업 파일명 |

#### 응답

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### 오류

- `400` — 파일명 누락 또는 백업을 찾을 수 없음
- `403` — 원격 접속

### POST /api/tools/backup/delete

지정된 백업을 삭제합니다. **localhost에서만 사용 가능합니다.**

#### Rate Limit

DESTRUCTIVE

#### 요청

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `filename` | string | 예 | 삭제할 백업 파일명 |

#### 응답

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

백업 시스템 상태를 가져옵니다.

#### 응답

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## 디버그 로그

### GET /api/tools/debug-log

디버그 로그의 끝부분을 가져옵니다. 디버그 모드가 비활성화되면 `enabled: false`를 반환합니다.

#### 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `limit` | int | `200` | 가져올 행 수 (1-5000) |
| `filter` | string | `""` | 행 필터 문자열 (부분 문자열 매칭) |

#### 응답

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

디버그 로그 파일을 다운로드합니다. **localhost에서만 사용 가능합니다.**

#### 응답

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### 오류

- `400` — 디버그 모드 미활성화
- `403` — 원격 접속
- `404` — 로그 파일을 찾을 수 없음

### POST /api/tools/debug-log/clear

디버그 로그를 삭제합니다. **localhost에서만 사용 가능합니다.**

#### Rate Limit

WRITE

#### 응답

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### 오류

- `400` — 디버그 모드 미활성화
- `403` — 원격 접속
- `404` — 로그 파일을 찾을 수 없음

---

## 아카이브 정리

중복 아카이브와 해당 압축 해제 폴더를 감지하고 정리하기 위한 도구입니다. 모든 엔드포인트는 **localhost에서만 사용 가능합니다.**

### POST /api/tools/archive-cleanup/scan

아카이브-폴더 쌍을 스캔합니다.

#### Rate Limit

HEAVY

#### 요청

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `path` | string | 필수 | 스캔할 디렉토리 |
| `recursive` | bool | `false` | 하위 디렉토리를 재귀적으로 스캔 |

#### 경로 유효성 검사

- `~`로 시작하는 경로는 거부됨
- `..`를 포함하는 경로는 거부됨

#### 응답

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

스캔된 쌍에 대해 정리 작업을 실행합니다.

#### Rate Limit

DESTRUCTIVE

#### 요청

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `actions` | array | 작업 배열 |
| `actions[].action` | string | `"delete_archive"`, `"delete_folder"` 또는 `"skip"` 중 하나 |
| `actions[].archive_path` | string | 작업이 `delete_archive`일 때 필수 |
| `actions[].folder_path` | string | 작업이 `delete_folder`일 때 필수 |

#### 응답

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

LLM을 사용하여 아카이브-폴더 쌍의 동일성을 검증합니다 (단일 쌍).

#### Rate Limit

HEAVY

#### 요청

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `archive_path` | string | 예 | 아카이브 파일 경로 |
| `folder_path` | string | 예 | 압축 해제 폴더 경로 |
| `pair_info` | object | 아니오 | 추가 쌍 메타데이터 |

#### 응답

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

LLM을 사용하여 여러 쌍을 일괄 검증합니다. 최대 50쌍.

#### Rate Limit

HEAVY

#### 요청

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| 파라미터 | 타입 | 제한 | 설명 |
|----------|------|------|------|
| `pairs` | array | 최대 50 | 검증할 쌍 배열 |

#### 응답

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

아카이브 정리 LLM 설정을 가져옵니다.

#### 응답

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

아카이브 정리 LLM 설정을 저장합니다.

#### Rate Limit

WRITE

#### 요청

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### 응답

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

지정된 엔진에서 사용 가능한 모델을 나열합니다.

#### 요청

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `engine` | string | 예 | `"ollama"` 또는 `"openai_compat"` |
| `base_url` | string | 예 | 엔진 API URL |
| `api_key` | string | 아니오 | `openai_compat`용 API Key |

#### 응답

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### 오류

- `400` — 유효하지 않은 엔진 또는 `base_url` 누락
