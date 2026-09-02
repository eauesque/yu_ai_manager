# Scan API

ファイルスキャン・スキャンルート管理に関する API。

## スキャン制御

### POST /api/scan/start

スキャンを開始する。

### リクエスト

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `root_indices` | int[] | スキャン対象のルートインデックス (省略時: 全ルート) |
| `force` | bool | 既存ファイルも再スキャン |

### レスポンス

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

スキャン進捗を取得。

### レスポンス

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

実行中のスキャンをキャンセル。

### GET /api/scan/interrupted

中断されたスキャンの情報を取得。

### POST /api/scan/resume

中断されたスキャンを再開。

### POST /api/scan/dismiss

中断されたスキャンの状態を破棄。

## スキャンワーカー CLI

v3.27.0 以降、スキャンは別プロセス (ワーカー) で実行されます。
WebUI の API に加えて、CLI から直接ワーカーを操作できます。

```bash
# スキャン開始
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# スキャン停止 (SIGTERM → graceful shutdown)
python -m core.scan.scan_worker stop

# 状態確認
python -m core.scan.scan_worker status
```

### IPC ファイル

| ファイル | 内容 |
|---------|------|
| `/tmp/yu-scan/worker.pid` | ワーカーの PID |
| `/tmp/yu-scan/progress.json` | 進捗 (JSON: running, phase, current, total, percent, message, detail, error) |

WebUI はこの進捗ファイルをポーリングし、`GET /api/scan/status` と SSE イベント (`scan.progress`, `scan.complete`) に変換して中継します。

## スキャンエラー

### GET /api/scan-errors

スキャン中に発生したエラー一覧。

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `type` | string | エラー種別フィルタ |
| `resolved` | bool | 解決済みのみ |
| `limit` | int | 取得件数 |

### POST /api/scan-errors/<id>/resolve

エラーを解決済みとしてマーク。

### POST /api/scan-errors/clear

解決済みエラーを一括削除。

## スキャンルート管理

### GET /api/scan-roots

登録済みスキャンルート一覧。

### レスポンス

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

スキャンルートを追加。

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

スキャンルートを更新 (パス変更)。

### DELETE /api/scan-roots/<index>

スキャンルートを削除。

### POST /api/scan-roots/<index>/toggle

スキャンルートの有効/無効を切り替え。

### POST /api/scan-roots/batch-toggle

全スキャンルートを一括で有効化または無効化。

```json
{ "enabled": true }
```

### POST /api/scan-roots/reorder

スキャンルートの順序を変更。

```json
{ "order": [2, 0, 1] }
```

`order` は新しい順に並べたインデックスの配列。

### POST /api/scan-all

全スキャンルートをバックグラウンドスキャン（`POST /api/scan/start` に `root_indices` 省略と同等）。

## スキャンキュー

スキャン待ち行列の管理。

### GET /api/scan/queue

キュー内のアイテム一覧を返す。

```json
{ "items": [...], "count": 3 }
```

### DELETE /api/scan/queue/<queue_id>

キューから特定アイテムを削除。

### POST /api/scan/queue/clear

キューを全消去。

```json
{ "status": "cleared", "cleared": 3 }
```

## スキャン履歴

### GET /api/scan/history

過去のスキャン実行履歴を新しい順に返す（admin scope 必須）。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `limit` | int | 50 | 取得件数上限 |

### POST /api/scan/history/clear

スキャン履歴を全削除。

## スキャン済みルート（デバッグ用）

### GET /api/scanned-roots

DB に登録されたファイルのルートディレクトリ一覧を返す。

### POST /api/scanned-roots/purge

指定パス配下のファイルレコードを DB から完全削除（注意: 元に戻せない）。

```json
{ "path": "/old/images" }
```

## ハッシュバックフィル

### POST /api/hash-backfill/start

既存ファイルのハッシュ値をバックグラウンド計算。

### GET /api/hash-backfill/status

進捗状況を取得。

### POST /api/hash-backfill/cancel

計算をキャンセル。

## バックグラウンドジョブ

### GET /api/jobs/status

全バックグラウンドジョブの状態。UI バナー表示用。

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
