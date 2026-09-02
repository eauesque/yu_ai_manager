# Events API (SSE)

Server-Sent Events によるリアルタイムイベント配信。

## GET /api/events/stream

メインイベントストリーム。全ページで共有される単一接続。

### 接続

```javascript
// TypeScript モジュールから
import { sseSubscribe } from '../sse';
sseSubscribe('scan.complete', (data) => { ... });

// テンプレート inline script から
window.sseSubscribe('scan.complete', (data) => { ... });
```

**注意**: `new EventSource()` を直接使用しないこと。`window.EventSource` は Proxy で上書きされており、直接利用するとエラーになります。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `types` | string | 購読するイベント型 (カンマ区切り、省略時: 全イベント) |

### 接続制限

- IP あたり最大 10 同時接続
- Visibility-aware: タブが非表示になると接続を縮退
- Exponential backoff による自動再接続

## イベント型一覧

### スキャン関連

| イベント | データ | 説明 |
|---------|--------|------|
| `scan.progress` | `{ scanned, total, current_file }` | スキャン進捗 |
| `scan.complete` | `{ added_count, updated_count, added_ids?, updated_ids? }` | スキャン完了 |
| `config.scan_roots_changed` | `{}` | スキャンルート変更通知 |

### お気に入り・コレクション

| イベント | データ | 説明 |
|---------|--------|------|
| `favorite.add` | `{ file_id, collection_id }` | お気に入り追加 |
| `favorite.remove` | `{ file_id, collection_id }` | お気に入り削除 |
| `collection.create` | `{ id, name }` | コレクション作成 |
| `collection.delete` | `{ id }` | コレクション削除 |

### AI 分析・タグ付け

| イベント | データ | 説明 |
|---------|--------|------|
| `semantic_index.start` | `{ total }` | CLIP インデックス開始 |
| `semantic_index.progress` | `{ done, total }` | CLIP インデックス進捗 |
| `semantic_index.complete` | `{ indexed }` | CLIP インデックス完了 |
| `vlm_caption.start` | `{ total }` | VLM キャプション開始 |
| `vlm_caption.progress` | `{ done, total }` | VLM キャプション進捗 |
| `vlm_caption.complete` | `{ processed }` | VLM キャプション完了 |
| `yolo_detect.start` | `{ total }` | YOLO 検出開始 |
| `yolo_detect.progress` | `{ done, total }` | YOLO 検出進捗 |
| `yolo_detect.complete` | `{ detected }` | YOLO 検出完了 |

### Freeze & Pull-back

| イベント | データ | 説明 |
|---------|--------|------|
| `fpb.start` | `{ job_id }` | ジョブ開始 |
| `fpb.progress` | `{ job_id, frame, total }` | フレーム進捗 |
| `fpb.complete` | `{ job_id, output_path }` | ジョブ完了 |
| `fpb.error` | `{ job_id, error }` | ジョブエラー |

### チャットログ

| イベント | データ | 説明 |
|---------|--------|------|
| `chatlog_reprocess.start` | `{ total }` | AI 再処理開始 |
| `chatlog_reprocess.progress` | `{ done, total }` | AI 再処理進捗 |
| `chatlog_reprocess.complete` | `{ processed }` | AI 再処理完了 |
| `chatlog_reprocess.error` | `{ error }` | AI 再処理エラー |

### スケジューラ

| イベント | データ | 説明 |
|---------|--------|------|
| `scheduler.job_executed` | `{ job_id, result }` | ジョブ実行完了 |
| `scheduler.job_error` | `{ job_id, error }` | ジョブ実行エラー |

## GET /api/logs/stream

サーバーログ専用 SSE ストリーム。メインストリームとは独立。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `level` | string | 最小ログレベル (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### イベント

| イベント | データ | 説明 |
|---------|--------|------|
| `log.entry` | `{ seq, ts, level, name, message }` | ログエントリ |

### 接続制限

- IP あたり最大 3 同時接続 (メインストリームとは別枠)
- 15 秒間隔のハートビート (`: heartbeat\n\n`)
