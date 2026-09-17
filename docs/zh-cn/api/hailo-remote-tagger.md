# Hailo Remote Tagger API

通过网络将图片发送至远程 Hailo AI HAT 推理服务器（如 Raspberry Pi 5），执行 Danbooru 标签推理并将结果保存至数据库的 API。

## 概述

即使本地没有 GPU 或 ONNX 运行时，也可以使用局域网上搭载 Hailo-10H 的设备作为远程标记器。图片以 multipart/form-data 方式发送，标签 JSON 作为响应返回。

---

## GET /api/hailo-tagger/config

获取当前配置。

### Rate Limit

READ（无限制）

### 响应

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | Hailo Remote Tagger 是否启用 |
| `endpoint_url` | string | Pi 端点 URL（例：`http://192.168.1.50:8080`）|
| `threshold` | float | 标签置信度阈值（仅保存高于此值的标签）|
| `timeout` | int | 请求超时时间（秒）|

---

## POST /api/hailo-tagger/config

保存配置。支持部分更新（仅更改指定字段）。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `enabled` | bool | 否 | 启用/禁用 |
| `endpoint_url` | string | 否 | Pi 端点 URL |
| `threshold` | float | 否 | 标签置信度阈值 |
| `timeout` | int | 否 | 请求超时时间（秒）|

### 请求示例

```json
{
  "enabled": true,
  "endpoint_url": "http://192.168.1.50:8080",
  "threshold": 0.35
}
```

### 响应

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

### 错误

| 状态码 | 说明 |
|--------|------|
| 400 | JSON 对象不正确 |

---

## GET /api/hailo-tagger/status

测试与 Hailo 端点的连接。向 `/health` 端点发送 GET 请求以验证可达性。

### Rate Limit

READ（无限制）

### 响应（成功）

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

### 响应（未配置/无法到达）

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

为单个文件添加标签。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 目标文件的数据库 ID |

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `force` | bool | 否 | 覆盖现有标签（默认：`false`）|

### 响应

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

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|------|
| 400 | `disabled` | Hailo Tagger 已禁用 |
| 400 | `not_configured` | 端点 URL 未配置 |
| 400 | `file_not_found` | 文件未找到 |
| 400 | `file_missing` | 磁盘上不存在该文件 |
| 400 | `unsupported_type` | 不支持此文件类型的标记 |
| 502 | `request_failed` | 无法连接至远程服务器 |

---

## POST /api/hailo-tagger/batch

批量标记多个文件。作为后台任务执行。

### Rate Limit

HEAVY（~20 req/min, burst 5）

### 请求体

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `file_ids` | int[] | 否 | 目标文件 ID 列表（最大 500）。省略时自动选择未标记文件 |
| `limit` | int | 否 | 自动选择时的最大数量（默认：100）|
| `force` | bool | 否 | 覆盖现有标签（默认：`false`）|

### 请求示例

```json
{
  "file_ids": [1, 2, 3, 4, 5],
  "force": false
}
```

### 响应

```json
{
  "ok": true,
  "data": {
    "started": true,
    "job_id": "hailo_tagger"
  }
}
```

### 错误

| 状态码 | 代码 | 说明 |
|--------|------|------|
| 400 | `batch_too_large` | file_ids 超过 500 条 |
| 409 | `job_running` | 批量任务已在运行中 |

---

## GET /api/hailo-tagger/tags/{file_id}

获取文件的 Hailo 标签。

### Rate Limit

READ（无限制）

### 响应

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

删除文件的所有 Hailo 标签。

### Rate Limit

DESTRUCTIVE（~12 req/min, burst 3）

### 响应

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

## 数据库结构

Hailo 标签存储在专用的 `file_hailo_tags` 数据表中（独立于 `file_wd_tags`）。

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

| 列 | 说明 |
|----|------|
| `file_id` | files 数据表的外键 |
| `tag_name` | Danbooru 标签名称（例：`1girl`, `solo`）|
| `confidence` | 推理置信度（0.0〜1.0）|
| `source` | 标签来源标识符（固定：`hailo_remote`）|
| `created_at` | UNIX 时间戳 |

---

## 配置

`config.json` 的 `hailo_tagger` 部分：

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

也可从设置页面更改。

> **Note**: 如需管理多个标签服务器，请使用 [Tagger Server Registry API](tagger-servers.md)。旧版配置可通过 `/api/tagger-servers/migrate` 自动迁移。Tagger Server Registry 也支持 Bearer 令牌认证。
