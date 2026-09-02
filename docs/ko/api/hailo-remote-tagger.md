# Hailo Remote Tagger API

네트워크를 통해 원격 Hailo AI HAT 추론 서버(예: Raspberry Pi 5)에 이미지를 전송하여 Danbooru 태그 추론을 실행하고 결과를 데이터베이스에 저장하는 API입니다.

## 개요

로컬에 GPU나 ONNX 런타임이 없어도 LAN의 Hailo-10H 장착 디바이스를 원격 태거로 사용할 수 있습니다. 이미지는 multipart/form-data로 전송되며, 태그 JSON이 응답으로 반환됩니다.

---

## GET /api/hailo-tagger/config

현재 설정을 가져옵니다.

### Rate Limit

READ (무제한)

### 응답

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": false,
      "endpoint_url": "",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `enabled` | bool | Hailo Remote Tagger 활성화 여부 |
| `endpoint_url` | string | Pi 엔드포인트 URL (예: `http://192.168.1.50:8080`) |
| `threshold` | float | 태그 신뢰도 임계값 (이 값 이상의 태그만 저장) |
| `timeout` | int | 요청 타임아웃 (초) |

---

## POST /api/hailo-tagger/config

설정을 저장합니다. 부분 업데이트 지원 (지정한 필드만 변경).

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `enabled` | bool | 아니오 | 활성화/비활성화 |
| `endpoint_url` | string | 아니오 | Pi 엔드포인트 URL |
| `threshold` | float | 아니오 | 태그 신뢰도 임계값 |
| `timeout` | int | 아니오 | 요청 타임아웃 (초) |

### 요청 예시

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### 응답

```json
{
  "ok": true,
  "data": {
    "config": {
      "enabled": true,
      "endpoint_url": "http://192.168.1.50:8080",
      "threshold": 0.35,
      "timeout": 30
    }
  }
}
```

### 오류

| 상태 코드 | 설명 |
|-----------|------|
| 400 | JSON 객체가 올바르지 않음 |

---

## GET /api/hailo-tagger/status

Hailo 엔드포인트 연결 테스트를 실행합니다. `/health` 엔드포인트에 GET 요청을 보내 도달 가능성을 확인합니다.

### Rate Limit

READ (무제한)

### 응답 (성공)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": true,
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

### 응답 (미설정/도달 불가)

```json
{
  "ok": true,
  "data": {
    "enabled": true,
    "reachable": false,
    "reason": "Connection refused",
    "endpoint_url": "http://192.168.1.50:8080"
  }
}
```

---

## POST /api/hailo-tagger/tag/{file_id}

단일 파일에 태그를 부여합니다.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### 경로 매개변수

| 매개변수 | 타입 | 설명 |
|----------|------|------|
| `file_id` | int | 대상 파일의 데이터베이스 ID |

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `force` | bool | 아니오 | 기존 태그 덮어쓰기 (기본값: `false`) |

### 응답

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "filepath": "/images/test.png",
    "tag_count": 15,
    "tags": [
      {"tag": "1girl", "confidence": 0.95},
      {"tag": "solo", "confidence": 0.88}
    ]
  }
}
```

### 오류

| 상태 코드 | 코드 | 설명 |
|-----------|------|------|
| 400 | `disabled` | Hailo Tagger가 비활성화됨 |
| 400 | `not_configured` | 엔드포인트 URL이 설정되지 않음 |
| 400 | `file_not_found` | 파일을 찾을 수 없음 |
| 400 | `file_missing` | 디스크에 파일이 존재하지 않음 |
| 400 | `unsupported_type` | 태그 부여를 지원하지 않는 파일 형식 |
| 502 | `request_failed` | 원격 서버에 연결할 수 없음 |

---

## POST /api/hailo-tagger/batch

여러 파일을 일괄 태그 부여합니다. 백그라운드 작업으로 실행됩니다.

### Rate Limit

HEAVY (~20 req/min, burst 5)

### 요청 본문

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file_ids` | int[] | 아니오 | 대상 파일 ID 목록 (최대 500). 생략 시 미태그 파일 자동 선택 |
| `limit` | int | 아니오 | 자동 선택 시 최대 수량 (기본값: 100) |
| `force` | bool | 아니오 | 기존 태그 덮어쓰기 (기본값: `false`) |

### 요청 예시

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### 응답

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### 오류

| 상태 코드 | 코드 | 설명 |
|-----------|------|------|
| 400 | `batch_too_large` | file_ids가 500건 초과 |
| 409 | `job_running` | 일괄 작업이 이미 실행 중 |

---

## GET /api/hailo-tagger/tags/{file_id}

파일의 Hailo 태그를 가져옵니다.

### Rate Limit

READ (무제한)

### 응답

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "tags": [
      {"tag_name": "1girl", "confidence": 0.95, "source": "hailo_remote", "created_at": 1710720000},
      {"tag_name": "solo", "confidence": 0.88, "source": "hailo_remote", "created_at": 1710720000}
    ]
  }
}
```

---

## DELETE /api/hailo-tagger/tags/{file_id}

파일의 모든 Hailo 태그를 삭제합니다.

### Rate Limit

DESTRUCTIVE (~12 req/min, burst 3)

### 응답

```json
{
  "ok": true,
  "data": {
    "file_id": 42,
    "deleted": 15
  }
}
```

---

## 데이터베이스 스키마

Hailo 태그는 전용 `file_hailo_tags` 테이블에 저장됩니다 (`file_wd_tags`와 독립).

```sql
CREATE TABLE file_hailo_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    source     TEXT NOT NULL DEFAULT 'hailo_remote',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name)
);
```

| 열 | 설명 |
|----|------|
| `file_id` | files 테이블의 외래 키 |
| `tag_name` | Danbooru 태그 이름 (예: `1girl`, `solo`) |
| `confidence` | 추론 신뢰도 (0.0~1.0) |
| `source` | 태그 출처 식별자 (고정: `hailo_remote`) |
| `created_at` | UNIX 타임스탬프 |

---

## 설정

`config.json`의 `hailo_tagger` 섹션:

```json
{
  "hailo_tagger": {
    "enabled": true,
    "endpoint_url": "http://192.168.1.50:8080",
    "threshold": 0.35,
    "timeout": 30
  }
}
```

설정 페이지에서도 변경할 수 있습니다.

> **Note**: 여러 태거 서버를 관리하려면 [Tagger Server Registry API](tagger-servers.md)를 사용하세요. 레거시 설정은 `/api/tagger-servers/migrate`로 자동 마이그레이션할 수 있습니다. Tagger Server Registry는 Bearer 토큰 인증도 지원합니다.
