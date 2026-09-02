# YOLO Stream API

YOLO 实时流处理相关 API。提供流源管理、MJPEG 传输、检测规则、录像与快照功能。

所有 POST/PUT/DELETE 端点需要 `X-Requested-With` 头（使用 Bearer API Key 时除外）。

---

## 源管理

### GET /ext/hailo-yolo/api/stream/sources

列出所有已注册的流源。

#### 响应

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

添加新的流源。

#### 请求

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 源的唯一标识符 |
| `url` | string | 是 | RTSP URL 或设备索引 |
| `name` | string | 否 | 显示名称 |

#### 响应 (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

移除指定源。

#### 响应

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

启动指定源的采集。

#### 响应

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

停止指定源的采集。

#### 响应

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

测试源连接。若请求中提供 URL 则测试该 URL，否则使用已有源的 URL。

#### 请求

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### 响应

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

检测已连接的 USB 摄像头。

#### 响应

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **说明：** Rust 原生响应仅在 Linux 上枚举 USB 摄像头，并且不会打开设备；`resolution` 始终为 `null`。Windows 和 macOS 返回 `devices: []`，也不支持按数字摄像头索引注册。
>
> 事件 fan-out 也会缩减：不再向已配置的 webhook 扩展隐式 wildcard 分发；自定义事件名匹配 `RELAY_TYPES` 时不再进行 LAN relay；不再到达专用 MCP 事件接收端。`mcp_event` 通过共享 SSE hub 分发。

---

## 视频流

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

返回带有 YOLO 检测叠加的 MJPEG 流。每个源最多 4 个同时观看者。

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## 规则管理

### GET /ext/hailo-yolo/api/stream/rules

列出所有规则。

#### 响应

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

添加新规则。在请求体中传入完整的规则 JSON。

#### 响应 (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

更新已有规则。

#### 响应

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

删除规则。

#### 响应

```json
{ "status": "ok" }
```

---

## 录像与快照

### GET /ext/hailo-yolo/api/stream/recordings

列出录像文件。

#### 响应

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

提供快照图片文件。

---

## 状态

### GET /ext/hailo-yolo/api/stream/status

获取管线与源的综合状态。

#### 响应

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

## 规则 JSON 结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 规则的唯一标识符 |
| `name` | string | 规则名称 |
| `enabled` | boolean | 启用标志 |
| `conditions.classes` | string[] | 检测目标类别（例：`["person"]`） |
| `conditions.min_confidence` | number | 最低置信度（0.0〜1.0） |
| `conditions.sources` | string[] | 目标源 ID。省略时应用全部源 |
| `conditions.schedule` | object | 调度（`start`、`end`、`days`） |
| `cooldown_sec` | number | 冷却秒数 |
| `actions` | object[] | 动作数组 |

### 动作类型

| type | 说明 |
|------|------|
| `snapshot` | 检测时保存快照 |
| `record` | 检测时开始录像 |
| `webhook` | 发送通知至 Webhook URL（含 HMAC 签名） |
| `sse` | 发送事件至 SSE 频道 |
| `mcp_event` | 触发 MCP 事件 |
