# Events API (SSE)

通过 Server-Sent Events 实现实时事件推送。

## GET /api/events/stream

主事件流。所有页面共享一个连接。

### 连接

```javascript
// 从 TypeScript 模块
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// 从模板内联脚本
window.sseSubscribe('scan.complete', (data) => { ... });
```

**重要**：请勿直接使用 `new EventSource()`。`window.EventSource` 已被 Proxy 覆盖，直接使用会导致错误。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `types` | string | 要订阅的事件类型（逗号分隔；省略则接收所有事件） |

### 连接限制

- 每个 IP 最多 10 个并发连接
- 可见性感知：标签页隐藏时连接进入节能状态
- 使用指数退避的自动重连

## 事件类型

### 扫描

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | 扫描进度 |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | 扫描完成 |
| `config.scan_roots_changed` | `{}` | 扫描根目录变更通知 |

### 收藏夹与合集

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | 添加收藏 |
| `favorite.remove` | `{ file_id, collection_id }` | 移除收藏 |
| `collection.create` | `{ id, name }` | 创建合集 |
| `collection.delete` | `{ id }` | 删除合集 |

### AI 分析与标签

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | CLIP 索引构建开始 |
| `semantic_index.progress` | `{ done, total }` | CLIP 索引构建进度 |
| `semantic_index.complete` | `{ indexed }` | CLIP 索引构建完成 |
| `vlm_caption.start` | `{ total }` | VLM 字幕生成开始 |
| `vlm_caption.progress` | `{ done, total }` | VLM 字幕生成进度 |
| `vlm_caption.complete` | `{ processed }` | VLM 字幕生成完成 |
| `yolo_detect.start` | `{ total }` | YOLO 检测开始 |
| `yolo_detect.progress` | `{ done, total }` | YOLO 检测进度 |
| `yolo_detect.complete` | `{ detected }` | YOLO 检测完成 |

### Freeze & Pull-back

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | 任务开始 |
| `fpb.progress` | `{ job_id, frame, total }` | 帧进度 |
| `fpb.complete` | `{ job_id, output_path }` | 任务完成 |
| `fpb.error` | `{ job_id, error }` | 任务错误 |

### 聊天日志

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | AI 重处理开始 |
| `chatlog_reprocess.progress` | `{ done, total }` | AI 重处理进度 |
| `chatlog_reprocess.complete` | `{ processed }` | AI 重处理完成 |
| `chatlog_reprocess.error` | `{ error }` | AI 重处理错误 |

### 调度器

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | 计划任务完成 |
| `scheduler.job_error` | `{ job_id, error }` | 计划任务错误 |

## GET /api/logs/stream

服务器日志专用 SSE 流。与主流独立运行。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `level` | string | 最低日志级别（`DEBUG`、`INFO`、`WARNING`、`ERROR`） |

### 事件

| 事件 | 数据 | 说明 |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | 日志条目 |

### 连接限制

- 每个 IP 最多 3 个并发连接（与主流分开计算）
- 15 秒心跳间隔（`: heartbeat\n\n`）
