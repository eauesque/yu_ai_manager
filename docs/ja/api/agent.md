# Agent Safety Gateway API

AI エージェントの安全管理に関する API。Kill Switch、Circuit Breaker、Budget、Action Journal、Approval Gate、Scope Fence、Auto-Approve、Tool Classification、Undo、Anomaly Detection、Audit Bureau の各機能を提供する。

全ての POST/DELETE エンドポイントには `X-Requested-With` ヘッダが必要（Bearer API Key 使用時を除く）。

---

## Kill Switch

### POST /api/agent/kill

Kill Switch を発動し、エージェントの全操作を即座に停止する。

#### レート制限

WRITE

#### リクエスト

```json
{
  "reason": "Manual kill via API"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `reason` | string | いいえ | 停止理由。省略時は `"Manual kill via API"` |

#### レスポンス

```json
{
  "ok": true,
  "status": {
    "killed": true,
    "reason": "Manual kill via API",
    "killed_at": "2026-03-22T12:00:00"
  }
}
```

### POST /api/agent/resume

Kill Switch を解除し、エージェントの操作を再開する。

#### レート制限

WRITE

#### リクエスト

なし（空ボディ）

#### レスポンス

```json
{
  "ok": true,
  "status": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  }
}
```

### GET /api/agent/status

Kill Switch、Circuit Breaker、Budget の統合ステータスを取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "kill_switch": {
    "killed": false,
    "reason": "",
    "killed_at": ""
  },
  "circuit_breaker": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  },
  "budget": {
    "session_id": "abc123",
    "used": 10,
    "limit": 100,
    "remaining": 90
  },
  "killed": false,
  "reason": "",
  "killed_at": ""
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `kill_switch` | object | Kill Switch の詳細ステータス |
| `circuit_breaker` | object | Circuit Breaker の詳細ステータス。取得失敗時は `{"enabled": false, "state": "unknown"}` |
| `budget` | object | Budget の詳細ステータス。取得失敗時は空オブジェクト |
| `killed` | boolean | Kill Switch の発動状態（後方互換用トップレベルフィールド） |
| `reason` | string | Kill Switch の停止理由（後方互換用） |
| `killed_at` | string | Kill Switch の発動日時（後方互換用） |

---

## Circuit Breaker

### GET /api/agent/circuit-breaker

Circuit Breaker の状態を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "enabled": true,
  "state": "closed",
  "failure_count": 0,
  "threshold": 5
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `enabled` | boolean | Circuit Breaker が有効か |
| `state` | string | 状態: `"closed"` (正常), `"open"` (遮断中), `"half_open"` (試行中) |
| `failure_count` | int | 連続失敗回数 |
| `threshold` | int | open に遷移する失敗回数閾値 |

### POST /api/agent/circuit-breaker/reset

Circuit Breaker を closed 状態にリセットする。

#### レート制限

WRITE

#### リクエスト

なし（空ボディ）

#### レスポンス

```json
{
  "ok": true,
  "status": {
    "enabled": true,
    "state": "closed",
    "failure_count": 0,
    "threshold": 5
  }
}
```

---

## Budget

### GET /api/agent/budget

現在のセッションの Budget 残量を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "session_id": "abc123",
  "used": 10,
  "limit": 100,
  "remaining": 90
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `session_id` | string | セッション ID |
| `used` | int | 使用済みカウント |
| `limit` | int | 上限値 |
| `remaining` | int | 残り回数 |

### POST /api/agent/budget/reset

Budget カウンターをリセットする。

#### レート制限

WRITE

#### リクエスト

なし（空ボディ）

#### レスポンス

```json
{
  "ok": true,
  "status": {
    "session_id": "abc123",
    "used": 0,
    "limit": 100,
    "remaining": 100
  }
}
```

---

## Action Journal

### GET /api/agent/journal

Action Journal を検索する。エージェントが実行した操作の履歴を取得。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `tool_name` | string | いいえ | ツール名でフィルタ |
| `status` | string | いいえ | ステータスでフィルタ |
| `session_id` | string | いいえ | セッション ID でフィルタ |
| `limit` | int | いいえ | 取得件数上限（デフォルト: 50、最大: 200） |
| `offset` | int | いいえ | オフセット（デフォルト: 0） |

#### レスポンス

```json
{
  "entries": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "status": "completed",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "result": {"ok": true},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "total": 1
}
```

### GET /api/agent/journal/stats

Action Journal の統計情報を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "total_entries": 150,
  "by_tool": {"add_tags": 50, "delete_tags": 30, "scan": 70},
  "by_status": {"completed": 140, "failed": 10}
}
```

---

## Approval Gate

### GET /api/agent/approval

承認待ちリクエストの一覧を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "pending": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "params": {},
      "requested_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/agent/approval/\<request_id\>

承認リクエストに応答する。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `request_id` | string | リクエスト ID (パスパラメータ) |

#### リクエスト

```json
{
  "decision": "allow"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `decision` | string | はい | `"allow"` (許可), `"deny"` (拒否), `"always_allow"` (常に許可) |

#### レスポンス

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "decision": "allow"
}
```

#### エラー

- `400`: `decision` が `allow`/`deny`/`always_allow` のいずれでもない場合
- `404`: リクエストが見つからないか、既に応答済みの場合

### GET /api/agent/approval/history

承認履歴を取得。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `limit` | int | いいえ | 取得件数上限（デフォルト: 50、最大: 200） |

#### レスポンス

```json
{
  "history": [
    {
      "request_id": "req_abc123",
      "tool_name": "purge_deleted",
      "decision": "allow",
      "decided_at": "2026-03-22T12:01:00"
    }
  ]
}
```

---

## Scope Fence

### GET /api/agent/scope

全セッションの Scope Fence 状態を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "sessions": {
    "abc123": {
      "preset": "tagger",
      "denied": ["purge_deleted", "hard_delete"],
      "name": "Tagger Bot",
      "expires_at": "2026-03-22T14:00:00"
    }
  },
  "count": 1
}
```

### GET /api/agent/scope/\<session_id\>

特定セッションのスコープを取得。

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `session_id` | string | セッション ID (パスパラメータ) |

#### レスポンス

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted", "hard_delete"],
  "name": "Tagger Bot",
  "expires_at": "2026-03-22T14:00:00"
}
```

#### エラー

- `404`: セッションスコープが見つからない場合

### POST /api/agent/scope/\<session_id\>

セッションスコープを設定する。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `session_id` | string | セッション ID (パスパラメータ) |

#### リクエスト

```json
{
  "preset": "tagger",
  "denied": ["purge_deleted"],
  "name": "Tagger Bot",
  "duration_hours": 2.0
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `preset` | string | いいえ | プリセット名: `"read_only"`, `"tagger"`, `"organizer"`, `"full_access"` |
| `denied` | string[] | いいえ | 拒否するツール名のリスト |
| `name` | string | いいえ | スコープの表示名 |
| `duration_hours` | number | いいえ | スコープの有効期限（時間単位） |

#### レスポンス

```json
{
  "ok": true,
  "scope": {
    "preset": "tagger",
    "denied": ["purge_deleted"],
    "name": "Tagger Bot",
    "expires_at": "2026-03-22T14:00:00"
  }
}
```

#### エラー

- `400`: `denied` がリストでない場合

### DELETE /api/agent/scope/\<session_id\>

セッションスコープを削除する。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `session_id` | string | セッション ID (パスパラメータ) |

#### レスポンス

```json
{
  "ok": true
}
```

---

## Auto-Approve Rules

### GET /api/agent/auto-approve

自動承認ルールの一覧を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "rules": [
    {
      "index": 0,
      "tool": "add_tags",
      "conditions": {"max_count": 10}
    }
  ]
}
```

### POST /api/agent/auto-approve

自動承認ルールを追加する。

#### レート制限

WRITE

#### リクエスト

```json
{
  "tool": "add_tags",
  "conditions": {"max_count": 10}
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `tool` | string | はい | 対象ツール名 |
| `conditions` | object | いいえ | 自動承認の条件。省略時は無条件で承認 |

#### レスポンス

```json
{
  "ok": true,
  "rule": {
    "index": 1,
    "tool": "add_tags",
    "conditions": {"max_count": 10}
  }
}
```

#### エラー

- `400`: `tool` が未指定の場合
- `400`: `conditions` が辞書でない場合

### DELETE /api/agent/auto-approve/\<index\>

自動承認ルールを削除する。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `index` | int | ルールのインデックス (パスパラメータ) |

#### レスポンス

```json
{
  "ok": true
}
```

#### エラー

- `404`: ルールが見つからない場合

---

## Tool Classification

### GET /api/agent/tool-levels

ツール分類情報を取得する。`tool` パラメータを指定すると特定ツールのレベルを返し、省略時は全体のサマリーとオーバーライド設定を返す。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `tool` | string | いいえ | ツール名。指定時はそのツールのレベルのみ返す |

#### レスポンス（ツール指定時）

```json
{
  "tool": "purge_deleted",
  "level": "destructive"
}
```

#### レスポンス（全体）

```json
{
  "summary": {
    "safe": ["list_files", "search_files"],
    "write": ["add_tags", "remove_tags"],
    "destructive": ["purge_deleted", "hard_delete"]
  },
  "overrides": {
    "custom_tool": "safe"
  }
}
```

---

## Undo

### POST /api/agent/undo/\<journal_id\>

Action Journal に記録された操作を取り消す。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `journal_id` | int | Journal エントリ ID (パスパラメータ) |

#### レスポンス

```json
{
  "ok": true,
  "journal_id": 1,
  "undone_action": "add_tags"
}
```

#### エラー

- `400`: undo に失敗した場合（取り消し不可能な操作、既に取り消し済み等）

### GET /api/agent/undoable

取り消し可能な操作の一覧を取得。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `session_id` | string | いいえ | セッション ID でフィルタ |
| `limit` | int | いいえ | 取得件数上限（デフォルト: 50、最大: 200） |

#### レスポンス

```json
{
  "items": [
    {
      "id": 1,
      "tool_name": "add_tags",
      "session_id": "abc123",
      "params": {"file_id": 42, "tags": ["landscape"]},
      "created_at": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

---

## Anomaly Detection

### GET /api/agent/anomaly

Anomaly Detection の状態を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "enabled": true,
  "window_minutes": 10,
  "thresholds": {
    "max_actions_per_window": 100,
    "max_errors_per_window": 20
  },
  "current": {
    "actions": 15,
    "errors": 0
  }
}
```

### GET /api/agent/anomaly/alerts

Anomaly Detection のアラート一覧を取得。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `limit` | int | いいえ | 取得件数上限（デフォルト: 50、最大: 200） |

#### レスポンス

```json
{
  "alerts": [
    {
      "id": 1,
      "type": "high_error_rate",
      "message": "Error rate exceeded threshold",
      "severity": "warning",
      "created_at": "2026-03-22T12:00:00"
    }
  ]
}
```

### POST /api/agent/anomaly/reset

Anomaly Detection の履歴とアラートをリセットする。

#### レート制限

WRITE

#### リクエスト

なし（空ボディ）

#### レスポンス

```json
{
  "ok": true
}
```

---

## Audit Bureau

### GET /api/agent/audit

Audit Bureau の状態を取得。

#### パラメータ

なし

#### レスポンス

```json
{
  "data": {
    "total_entries": 500,
    "unacknowledged": 3,
    "last_report_at": "2026-03-22T00:00:00"
  }
}
```

### GET /api/agent/audit/log

Audit Log を検索する。

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `event_type` | string | いいえ | イベント種別でフィルタ |
| `severity` | string | いいえ | 重要度でフィルタ |
| `source` | string | いいえ | ソースでフィルタ |
| `unacknowledged` | string | いいえ | `"1"` または `"true"` で未確認のみ取得 |
| `limit` | int | いいえ | 取得件数上限（デフォルト: 50、最大: 200） |
| `offset` | int | いいえ | オフセット（デフォルト: 0） |

#### レスポンス

```json
{
  "data": {
    "entries": [
      {
        "id": 1,
        "event_type": "kill_switch_activated",
        "severity": "critical",
        "source": "api",
        "message": "Kill switch activated: Manual kill via API",
        "acknowledged": false,
        "created_at": "2026-03-22T12:00:00"
      }
    ],
    "total": 1
  }
}
```

### POST /api/agent/audit/acknowledge/\<audit_id\>

Audit Log エントリをユーザー確認済みとしてマークする。

#### レート制限

WRITE

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `audit_id` | int | Audit Log エントリ ID (パスパラメータ) |

#### レスポンス

```json
{
  "ok": true,
  "audit_id": 1
}
```

#### エラー

- `404`: エントリが見つからないか、既に確認済みの場合

### POST /api/agent/audit/report

Audit Bureau の定期レポートを手動生成する。

#### レート制限

WRITE

#### リクエスト

```json
{
  "hours": 24
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `hours` | int | いいえ | レポート対象期間（時間単位）。デフォルト: 24、最大: 720 |

#### レスポンス

```json
{
  "data": {
    "period_hours": 24,
    "total_events": 150,
    "by_severity": {"critical": 2, "warning": 10, "info": 138},
    "by_type": {"kill_switch_activated": 2, "approval_denied": 5},
    "generated_at": "2026-03-22T12:00:00"
  }
}
```
