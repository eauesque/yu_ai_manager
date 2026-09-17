# Events API (SSE)

透過 Server-Sent Events 實現即時事件推送。

## GET /api/events/stream

主事件串流。所有頁面共享一個連線。

### 連線

```javascript
// 從 TypeScript 模組
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// 從範本內嵌腳本
window.sseSubscribe('scan.complete', (data) => { ... });
```

**重要**：請勿直接使用 `new EventSource()`。`window.EventSource` 已被 Proxy 覆寫，直接使用會導致錯誤。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `types` | string | 要訂閱的事件類型（逗號分隔；省略則接收所有事件） |

### 連線限制

- 每個 IP 最多 10 個同時連線
- 可見性感知：分頁隱藏時連線進入節能狀態
- 使用指數退避的自動重連

## 事件類型

### 掃描

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `scan.progress` | `{ scanned, total, current_file }` | 掃描進度 |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | 掃描完成 |
| `config.scan_roots_changed` | `{}` | 掃描根目錄變更通知 |

### 我的最愛與合集

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `favorite.add` | `{ file_id, collection_id }` | 新增最愛 |
| `favorite.remove` | `{ file_id, collection_id }` | 移除最愛 |
| `collection.create` | `{ id, name }` | 建立合集 |
| `collection.delete` | `{ id }` | 刪除合集 |

### AI 分析與標籤

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `semantic_index.start` | `{ total }` | CLIP 索引建置開始 |
| `semantic_index.progress` | `{ done, total }` | CLIP 索引建置進度 |
| `semantic_index.complete` | `{ indexed }` | CLIP 索引建置完成 |
| `vlm_caption.start` | `{ total }` | VLM 字幕生成開始 |
| `vlm_caption.progress` | `{ done, total }` | VLM 字幕生成進度 |
| `vlm_caption.complete` | `{ processed }` | VLM 字幕生成完成 |
| `yolo_detect.start` | `{ total }` | YOLO 偵測開始 |
| `yolo_detect.progress` | `{ done, total }` | YOLO 偵測進度 |
| `yolo_detect.complete` | `{ detected }` | YOLO 偵測完成 |

### Freeze & Pull-back

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `fpb.start` | `{ job_id }` | 工作開始 |
| `fpb.progress` | `{ job_id, frame, total }` | 影格進度 |
| `fpb.complete` | `{ job_id, output_path }` | 工作完成 |
| `fpb.error` | `{ job_id, error }` | 工作錯誤 |

### 聊天紀錄

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `chatlog_reprocess.start` | `{ total }` | AI 重新處理開始 |
| `chatlog_reprocess.progress` | `{ done, total }` | AI 重新處理進度 |
| `chatlog_reprocess.complete` | `{ processed }` | AI 重新處理完成 |
| `chatlog_reprocess.error` | `{ error }` | AI 重新處理錯誤 |

### 排程器

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `scheduler.job_executed` | `{ job_id, result }` | 排程任務完成 |
| `scheduler.job_error` | `{ job_id, error }` | 排程任務錯誤 |

## GET /api/logs/stream

伺服器日誌專用 SSE 串流。與主串流獨立運作。

### 參數

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `level` | string | 最低日誌等級（`DEBUG`、`INFO`、`WARNING`、`ERROR`） |

### 事件

| 事件 | 資料 | 說明 |
|-------|------|-------------|
| `log.entry` | `{ seq, ts, level, name, message }` | 日誌項目 |

### 連線限制

- 每個 IP 最多 3 個同時連線（與主串流分開計算）
- 15 秒心跳間隔（`: heartbeat\n\n`）
