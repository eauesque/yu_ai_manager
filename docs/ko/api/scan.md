# Scan API

파일 스캔 및 스캔 루트 관리를 위한 API입니다.

## 스캔 제어

### POST /api/scan/start

스캔을 시작합니다.

### 요청

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| 필드 | 타입 | 설명 |
|-------|------|-------------|
| `root_indices` | int[] | 스캔할 루트의 인덱스 (생략 시 모든 루트) |
| `force` | bool | 기존 파일 재스캔 |

### 응답

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

스캔 진행 상황을 조회합니다.

### 응답

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

실행 중인 스캔을 취소합니다.

### GET /api/scan/interrupted

중단된 스캔 정보를 조회합니다.

### POST /api/scan/resume

중단된 스캔을 재개합니다.

### POST /api/scan/dismiss

중단된 스캔 상태를 폐기합니다.

## Scan Worker CLI

v3.27.0부터 스캔은 별도 프로세스(worker)에서 실행됩니다.
WebUI API 외에도 CLI에서 직접 worker를 제어할 수 있습니다.

```bash
# 스캔 시작
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# 스캔 중지 (SIGTERM -> 정상 종료)
python -m core.scan.scan_worker stop

# 상태 확인
python -m core.scan.scan_worker status
```

### IPC 파일

| 파일 | 내용 |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | 진행 상황 (JSON: running, phase, current, total, percent, message, detail, error) |

WebUI는 이 진행 상황 파일을 폴링하여 `GET /api/scan/status` 및 SSE 이벤트(`scan.progress`, `scan.complete`)를 통해 데이터를 전달합니다.

## 스캔 오류

### GET /api/scan-errors

스캔 중 발생한 오류 목록입니다.

| 파라미터 | 타입 | 설명 |
|-----------|------|-------------|
| `type` | string | 오류 유형 필터 |
| `resolved` | bool | 해결된 오류만 |
| `limit` | int | 결과 수 |

### POST /api/scan-errors/<id>/resolve

오류를 해결됨으로 표시합니다.

### POST /api/scan-errors/clear

해결된 모든 오류를 일괄 삭제합니다.

## 스캔 루트 관리

### GET /api/scan-roots

등록된 스캔 루트를 나열합니다.

### 응답

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

스캔 루트를 추가합니다.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

스캔 루트를 업데이트합니다 (경로 변경, 활성화/비활성화 전환).

### DELETE /api/scan-roots/<index>

스캔 루트를 삭제합니다.

## 해시 백필

### POST /api/hash-backfill/start

기존 파일에 대한 백그라운드 해시 계산을 시작합니다.

### GET /api/hash-backfill/status

진행 상황을 조회합니다.

### POST /api/hash-backfill/cancel

계산을 취소합니다.

## 백그라운드 작업

### GET /api/jobs/status

모든 백그라운드 작업의 상태입니다. UI 배너 표시에 사용됩니다.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
