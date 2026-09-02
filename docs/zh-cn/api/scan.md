# Scan API

文件扫描和扫描根目录管理的 API。

## 扫描控制

### POST /api/scan/start

启动扫描。

### 请求

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| 字段 | 类型 | 说明 |
|-------|------|-------------|
| `root_indices` | int[] | 要扫描的根目录索引（省略则扫描所有根目录） |
| `force` | bool | 重新扫描已有文件 |

### 响应

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

获取扫描进度。

### 响应

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

取消正在运行的扫描。

### GET /api/scan/interrupted

获取被中断的扫描信息。

### POST /api/scan/resume

恢复被中断的扫描。

### POST /api/scan/dismiss

丢弃中断的扫描状态。

## Scan Worker CLI

从 v3.27.0 起，扫描在单独的进程（worker）中运行。
除了 WebUI API 外，还可以通过 CLI 直接控制 worker。

```bash
# 启动扫描
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# 停止扫描（SIGTERM -> 优雅关闭）
python -m core.scan.scan_worker stop

# 检查状态
python -m core.scan.scan_worker status
```

### IPC 文件

| 文件 | 内容 |
|------|---------|
| `/tmp/yu-scan/worker.pid` | Worker PID |
| `/tmp/yu-scan/progress.json` | 进度（JSON: running, phase, current, total, percent, message, detail, error） |

WebUI 轮询此进度文件，并通过 `GET /api/scan/status` 和 SSE 事件（`scan.progress`、`scan.complete`）传递数据。

## 扫描错误

### GET /api/scan-errors

扫描期间发生的错误列表。

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `type` | string | 错误类型筛选 |
| `resolved` | bool | 仅已解决的错误 |
| `limit` | int | 结果数量 |

### POST /api/scan-errors/<id>/resolve

将错误标记为已解决。

### POST /api/scan-errors/clear

一次性删除所有已解决的错误。

## 扫描根目录管理

### GET /api/scan-roots

列出已注册的扫描根目录。

### 响应

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

添加扫描根目录。

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

更新扫描根目录（更改路径、切换启用/禁用）。

### DELETE /api/scan-roots/<index>

删除扫描根目录。

## 哈希回填

### POST /api/hash-backfill/start

启动现有文件的后台哈希计算。

### GET /api/hash-backfill/status

获取进度。

### POST /api/hash-backfill/cancel

取消计算。

## 后台任务

### GET /api/jobs/status

所有后台任务的状态。用于 UI 横幅显示。

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
