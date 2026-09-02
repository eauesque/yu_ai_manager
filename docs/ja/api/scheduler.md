# Scheduler API

タスクスケジューラの管理 API。定期実行ジョブの状態確認・追加・削除・一時停止・再開・即時実行、および実行履歴の取得が可能です。

## 設定

`config.json` でスケジューラの有効化とビルトインジョブのスケジュールを設定します:

```json
{
  "scheduler": {
    "enabled": true,
    "jobs": {
      "db_vacuum": { "enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0 },
      "db_integrity_check": { "enabled": true, "trigger": "cron", "hour": 4, "minute": 0 },
      "thumbnail_cleanup": { "enabled": true, "trigger": "cron", "hour": 5, "minute": 0 }
    }
  }
}
```

### ビルトインジョブ

| ジョブ ID | 説明 | デフォルトスケジュール |
|-----------|------|----------------------|
| `db_vacuum` | データベース VACUUM（容量回収） | 毎週日曜 03:00 |
| `db_integrity_check` | データベース整合性チェック | 毎日 04:00 |
| `thumbnail_cleanup` | サムネイルキャッシュ清掃 | 毎日 05:00 |
| `github_issue_poll` | GitHub Issue ポーリング | 未設定（WebUI から追加） |
| `bsky_notification_poll` | Bluesky 通知ポーリング | 未設定（WebUI から追加） |
| `prune_unused_tags` | 未使用タグの削除 | 未設定（WebUI から追加） |
| `refresh_monthly_stats` | 月次統計キャッシュの更新 | 未設定（WebUI から追加） |
| `rebuild_groups_index` | グループインデックスの再構築 | 未設定（WebUI から追加） |
| `db_backup` | データベースバックアップ | 未設定（WebUI から追加） |

## GET /api/scheduler/status

スケジューラの状態と全ジョブの情報を返します。

### レスポンス

| フィールド | 型 | 説明 |
|-----------|------|------|
| `ok` | boolean | 成功フラグ |
| `data.running` | boolean | スケジューラが稼働中か |
| `data.jobs` | array | ジョブ一覧 (次回実行時刻含む) |

### 例

```bash
curl "http://localhost:5100/api/scheduler/status"
```

```json
{
  "ok": true,
  "data": {
    "running": true,
    "jobs": [
      {
        "job_id": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      },
      {
        "job_id": "db_integrity_check",
        "trigger": "cron",
        "next_run": "2026-03-16T04:00:00",
        "paused": false
      }
    ]
  }
}
```

## GET /api/scheduler/jobs

ジョブ一覧を `next_run` 付きで返します。

### レスポンス

| フィールド | 型 | 説明 |
|-----------|------|------|
| `ok` | boolean | 成功フラグ |
| `data.jobs` | array | ジョブオブジェクトの配列 |
| `data.jobs[].job_id` | string | ジョブ ID |
| `data.jobs[].func_name` | string | 実行関数名 |
| `data.jobs[].trigger` | string | トリガー種別 (`cron`, `interval`, `date`) |
| `data.jobs[].next_run` | string | 次回実行予定時刻 (ISO 8601) |
| `data.jobs[].paused` | boolean | 一時停止中か |

### 例

```bash
curl "http://localhost:5100/api/scheduler/jobs"
```

```json
{
  "ok": true,
  "data": {
    "jobs": [
      {
        "job_id": "db_vacuum",
        "func_name": "db_vacuum",
        "trigger": "cron",
        "next_run": "2026-03-22T03:00:00",
        "paused": false
      }
    ]
  }
}
```

## POST /api/scheduler/jobs

カスタムジョブを追加します。

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `job_id` | string | Yes | 一意のジョブ ID |
| `func_name` | string | Yes | 実行する関数名 |
| `trigger` | string | Yes | トリガー種別 (`cron`, `interval`, `date`) |
| `trigger_args` | object | Yes | トリガー引数 (`hour`, `minute`, `day_of_week` 等) |

### 例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{
       "job_id": "custom_cleanup",
       "func_name": "thumbnail_cleanup",
       "trigger": "cron",
       "trigger_args": { "hour": 6, "minute": 30 }
     }'
```

```json
{
  "ok": true,
  "data": {
    "job_id": "custom_cleanup",
    "next_run": "2026-03-16T06:30:00"
  }
}
```

## DELETE /api/scheduler/jobs/\<id\>

指定したジョブを削除します。**DESTRUCTIVE** ティアのレートリミットが適用されます。

### パスパラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | string | ジョブ ID |

### 例

```bash
curl -X DELETE "http://localhost:5100/api/scheduler/jobs/custom_cleanup" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "removed": "custom_cleanup" }
}
```

## POST /api/scheduler/jobs/\<id\>/pause

ジョブを一時停止します。

### 例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/pause" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": true }
}
```

## POST /api/scheduler/jobs/\<id\>/resume

一時停止中のジョブを再開します。

### 例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/resume" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "paused": false }
}
```

## POST /api/scheduler/jobs/\<id\>/trigger

ジョブを即時実行します。**WRITE** ティアのレートリミットが適用されます。

### 例

```bash
curl -X POST "http://localhost:5100/api/scheduler/jobs/db_vacuum/trigger" \
     -H "X-Requested-With: XMLHttpRequest"
```

```json
{
  "ok": true,
  "data": { "job_id": "db_vacuum", "triggered": true }
}
```

## GET /api/scheduler/history

実行履歴を新しい順に返します (最大 100 件)。

### レスポンス

| フィールド | 型 | 説明 |
|-----------|------|------|
| `ok` | boolean | 成功フラグ |
| `data.history` | array | 実行履歴の配列 |
| `data.history[].job_id` | string | ジョブ ID |
| `data.history[].executed_at` | string | 実行日時 (ISO 8601) |
| `data.history[].status` | string | 結果 (`success`, `error`) |
| `data.history[].duration_ms` | number | 実行時間 (ミリ秒) |
| `data.history[].error` | string\|null | エラーメッセージ (失敗時のみ) |

### 例

```bash
curl "http://localhost:5100/api/scheduler/history"
```

```json
{
  "ok": true,
  "data": {
    "history": [
      {
        "job_id": "db_integrity_check",
        "executed_at": "2026-03-15T04:00:02",
        "status": "success",
        "duration_ms": 1234,
        "error": null
      },
      {
        "job_id": "thumbnail_cleanup",
        "executed_at": "2026-03-15T05:00:01",
        "status": "success",
        "duration_ms": 567,
        "error": null
      }
    ]
  }
}
```

## SSE イベント

スケジューラ関連のイベントは SSE 共有エンジン経由で配信されます。

| イベント | データ | 説明 |
|---------|--------|------|
| `scheduler.job_executed` | `{ job_id, result }` | ジョブ実行完了 |
| `scheduler.job_error` | `{ job_id, error }` | ジョブ実行エラー |

```javascript
window.sseSubscribe('scheduler.job_executed', (data) => {
  console.log(`Job ${data.job_id} completed: ${data.result}`);
});
```

## MCP ツール

| ツール名 | 説明 |
|---------|------|
| `get_scheduler_status` | スケジューラの稼働状態を取得 |
| `list_scheduled_jobs` | 登録済みジョブ一覧を取得 |
| `trigger_scheduled_job` | ジョブを即時実行 |
| `pause_scheduled_job` | ジョブを一時停止 |
| `resume_scheduled_job` | ジョブを再開 |
| `get_scheduler_history` | 実行履歴を取得 |

## レートリミット

| エンドポイント | メソッド | ティア |
|--------------|---------|--------|
| `/api/scheduler/status` | GET | READ (無制限) |
| `/api/scheduler/jobs` | GET | READ (無制限) |
| `/api/scheduler/jobs` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>` | DELETE | DESTRUCTIVE (~12 req/min) |
| `/api/scheduler/jobs/<id>/pause` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/resume` | POST | WRITE (~120 req/min) |
| `/api/scheduler/jobs/<id>/trigger` | POST | WRITE (~120 req/min) |
| `/api/scheduler/history` | GET | READ (無制限) |
