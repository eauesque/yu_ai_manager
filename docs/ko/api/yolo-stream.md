# YOLO Stream API

YOLO 실시간 스트림 처리 관련 API. 스트림 소스 관리, MJPEG 전송, 탐지 규칙, 녹화 및 스냅샷 기능을 제공합니다.

모든 POST/PUT/DELETE 엔드포인트에는 `X-Requested-With` 헤더가 필요합니다 (Bearer API Key 사용 시 제외).

---

## 소스 관리

### GET /ext/hailo-yolo/api/stream/sources

등록된 모든 스트림 소스를 목록 조회합니다.

#### 응답

```json
{
  "status": "ok",
  "sources": [
    {
      "id": "cam1",
      "name": "Front Camera",
      "url": "rtsp://192.168.1.100:554/stream",
      "type": "rtsp",
      "state": "running",
      "resolution": { "width": 1920, "height": 1080 },
      "fps": 25.0,
      "frame_count": 15420,
      "error": null,
      "viewers": 1
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/sources

새 스트림 소스를 추가합니다.

#### 요청

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `id` | string | 예 | 소스의 고유 식별자 |
| `url` | string | 예 | RTSP URL 또는 디바이스 인덱스 |
| `name` | string | 아니오 | 표시 이름 |

#### 응답 (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

지정된 소스를 제거합니다.

#### 응답

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

지정된 소스의 캡처를 시작합니다.

#### 응답

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

지정된 소스의 캡처를 중지합니다.

#### 응답

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

소스 연결을 테스트합니다. 요청 본문에 URL을 제공하면 해당 URL을 테스트하고, 생략 시 기존 소스의 URL을 사용합니다.

#### 요청

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### 응답

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

연결된 USB 카메라를 감지합니다.

#### 응답

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **참고:** Rust 네이티브 응답은 Linux에서만 USB 카메라를 열지 않고 열거하며, `resolution`은 항상 `null`입니다. Windows와 macOS는 `devices: []`를 반환하고 숫자 카메라 인덱스 등록을 지원하지 않습니다.
>
> 이벤트 fan-out도 축소됩니다. 구성된 webhook 확장으로의 암시적 wildcard 전달, 사용자 지정 이벤트 이름이 `RELAY_TYPES`와 일치할 때의 LAN relay, 전용 MCP 이벤트 수신처가 사라집니다. `mcp_event`는 공유 SSE hub를 통해 전달됩니다.

---

## 비디오 스트림

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

YOLO 탐지 오버레이가 포함된 MJPEG 스트림을 반환합니다. 소스당 최대 4명 동시 시청 가능.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## 규칙 관리

### GET /ext/hailo-yolo/api/stream/rules

모든 규칙을 목록 조회합니다.

#### 응답

```json
{
  "status": "ok",
  "rules": [
    {
      "id": "rule1",
      "name": "Person detection",
      "enabled": true,
      "conditions": {
        "classes": ["person"],
        "min_confidence": 0.7,
        "sources": ["cam1"],
        "schedule": { "start": "22:00", "end": "06:00", "days": ["mon","tue","wed","thu","fri","sat","sun"] }
      },
      "cooldown_sec": 60,
      "actions": [
        { "type": "snapshot", "save_dir": "./detections/snapshots" },
        { "type": "record", "save_dir": "./detections/videos", "duration_sec": 30, "extend_mode": "fixed" },
        { "type": "webhook", "url": "https://example.com/hook", "secret": "hmac-key" },
        { "type": "sse", "channel": "yolo_stream" },
        { "type": "mcp_event", "event": "yolo_stream.detection" }
      ]
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/rules

새 규칙을 추가합니다. 요청 본문에 전체 규칙 JSON을 전달합니다.

#### 응답 (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

기존 규칙을 업데이트합니다.

#### 응답

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

규칙을 삭제합니다.

#### 응답

```json
{ "status": "ok" }
```

---

## 녹화 및 스냅샷

### GET /ext/hailo-yolo/api/stream/recordings

녹화 파일을 목록 조회합니다.

#### 응답

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

스냅샷 이미지 파일을 제공합니다.

---

## 상태

### GET /ext/hailo-yolo/api/stream/status

파이프라인 및 소스의 종합 상태를 조회합니다.

#### 응답

```json
{
  "status": "ok",
  "pipeline": { "running": true, "queue_size": 2, "fps": 24.8 },
  "sources": [ { "id": "cam1", "state": "running" } ],
  "rules_count": 3,
  "recorder": { "active_recordings": 1 }
}
```

---

## 규칙 JSON 구조

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 규칙의 고유 식별자 |
| `name` | string | 규칙 이름 |
| `enabled` | boolean | 활성화 플래그 |
| `conditions.classes` | string[] | 탐지 대상 클래스 (예: `["person"]`) |
| `conditions.min_confidence` | number | 최소 신뢰도 (0.0~1.0) |
| `conditions.sources` | string[] | 대상 소스 ID. 생략 시 모든 소스에 적용 |
| `conditions.schedule` | object | 스케줄 (`start`, `end`, `days`) |
| `cooldown_sec` | number | 쿨다운 초 |
| `actions` | object[] | 액션 배열 |

### 액션 타입

| type | 설명 |
|------|------|
| `snapshot` | 탐지 시 스냅샷 저장 |
| `record` | 탐지 시 녹화 시작 |
| `webhook` | Webhook URL로 알림 전송 (HMAC 서명 포함) |
| `sse` | SSE 채널에 이벤트 전송 |
| `mcp_event` | MCP 이벤트 발행 |
