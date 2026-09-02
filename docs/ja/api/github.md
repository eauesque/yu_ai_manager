# GitHub Integration API

GitHub アカウント管理、Issue/PR/通知/リリースの操作に関する API。

Extension `builtin-github` が提供するエンドポイント群。全エンドポイントで認証 (PIN セッションまたは API Key) が必要。

## アカウント管理

### GET /api/github/accounts

登録済み GitHub アカウント一覧を取得。トークンはマスクされて返却される。

### レスポンス

```json
{
  "data": [
    {
      "label": "my-account",
      "token": "ghp_****...xxxx",
      "repos": ["owner/repo1", "owner/repo2"],
      "enabled": true
    }
  ]
}
```

### POST /api/github/accounts

新しい GitHub アカウントを登録。

### リクエスト

```json
{
  "label": "my-account",
  "token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "repos": ["owner/repo1", "owner/repo2"]
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `label` | string | Yes | アカウント識別ラベル (一意) |
| `token` | string | Yes | GitHub Personal Access Token |
| `repos` | string[] | Yes | 監視対象リポジトリ一覧 (`owner/repo` 形式) |

### レスポンス

```json
{
  "data": { "label": "my-account", "status": "created" }
}
```

### PUT /api/github/accounts/<label>

既存アカウントの設定を更新。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |

### リクエスト

```json
{
  "token": "ghp_new_token_value",
  "repos": ["owner/repo1", "owner/repo3"],
  "enabled": false
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `token` | string | No | 新しいトークン |
| `repos` | string[] | No | 監視対象リポジトリの更新 |
| `enabled` | boolean | No | アカウントの有効/無効 |

### DELETE /api/github/accounts/<label>

アカウントを削除。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |

---

## Issue

### GET /api/github/issues/<label>

指定アカウントのリポジトリから Issue 一覧を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |
| `state` | string | Issue 状態フィルタ (`open`, `closed`, `all`) |
| `labels` | string | ラベルフィルタ (カンマ区切り) |
| `since` | string | 指定日時以降の Issue (ISO 8601) |
| `repo` | string | 特定リポジトリに絞り込み (`owner/repo`) |

### curl 例

```bash
curl -H "Authorization: Bearer sk_xxxxx" \
  "http://localhost:5000/api/github/issues/my-account?state=open&repo=owner/repo1"
```

### POST /api/github/issues/<label>

新しい Issue を作成。

### リクエスト

```json
{
  "repo": "owner/repo1",
  "title": "Bug: ログイン画面でクラッシュ",
  "body": "再現手順:\n1. ...\n2. ...",
  "labels": ["bug", "priority:high"]
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `repo` | string | Yes | 対象リポジトリ (`owner/repo`) |
| `title` | string | Yes | Issue タイトル |
| `body` | string | No | Issue 本文 (Markdown) |
| `labels` | string[] | No | 付与するラベル |

### GET /api/github/issue/<label>/<repo>/<number>

Issue の詳細情報をコメント付きで取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル |
| `repo` | string | リポジトリ名 (`owner/repo`) |
| `number` | int | Issue 番号 |

### POST /api/github/triage/<label>

Issue のトリアージ (分類・優先度付け) を実行。

### リクエスト

```json
{
  "state": "open",
  "since": "2026-03-01T00:00:00Z"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `state` | string | No | 対象 Issue の状態フィルタ |
| `since` | string | No | 指定日時以降の Issue のみ (ISO 8601) |

---

## Pull Request

### GET /api/github/pulls/<label>

PR 一覧を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |
| `state` | string | PR 状態 (`open`, `closed`, `all`) |
| `repo` | string | 特定リポジトリに絞り込み (`owner/repo`) |

### GET /api/github/pull/<label>/<repo>/<number>

PR の詳細情報を変更ファイル一覧付きで取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル |
| `repo` | string | リポジトリ名 (`owner/repo`) |
| `number` | int | PR 番号 |

---

## 通知

### GET /api/github/notifications/<label>

通知一覧を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |
| `all` | string | `true` で既読含む全通知を取得 (デフォルト: 未読のみ) |

### PATCH /api/github/notifications/<label>/<thread_id>

指定スレッドを既読にする。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル |
| `thread_id` | string | 通知スレッド ID |

### POST /api/github/notifications/<label>/mark-all-read

全通知を既読にする。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |

---

## Discussion

### GET /api/github/discussions/<label>

GitHub Discussions を取得 (GraphQL API 経由)。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |
| `repo` | string | 特定リポジトリに絞り込み (`owner/repo`) |

---

## リリース

### GET /api/github/releases/<label>

リリース一覧を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |
| `repo` | string | 特定リポジトリに絞り込み (`owner/repo`) |

---

## リポジトリ統計

### GET /api/github/repo-stats/<label>/<repo>

単一リポジトリの統計情報を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル |
| `repo` | string | リポジトリ名 (`owner/repo`) |

### GET /api/github/repo-stats-all/<label>

登録済み全リポジトリの統計情報を一括取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |

---

## レートリミット

### GET /api/github/rate-limit/<label>

GitHub API のレートリミット残量を確認。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `label` | string | アカウントラベル (パスパラメータ) |

### レスポンス例

```json
{
  "data": {
    "rate": {
      "limit": 5000,
      "remaining": 4832,
      "reset": 1710500000
    }
  }
}
```

---

## トリアージプロンプト

### GET /api/github/triage-prompts

Issue/PR/Discussion 用の編集可能なトリアージプロンプトとデフォルト値を取得。

### レスポンス

```json
{
  "data": {
    "prompts": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    },
    "defaults": {
      "issue": "Review the following GitHub issue...",
      "pr": "Do not accept pull requests. Close automatically.",
      "discussion": "Discussions are closed. No action required."
    }
  }
}
```

### PUT /api/github/triage-prompts

トリアージプロンプトを更新。指定されたフィールドのみ更新される。

### リクエスト

```json
{
  "issue": "カスタム Issue トリアージプロンプト...",
  "pr": "カスタム PR プロンプト...",
  "discussion": "カスタム Discussion プロンプト..."
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `issue` | string | No | Issue 用トリアージプロンプト |
| `pr` | string | No | Pull Request 用トリアージプロンプト |
| `discussion` | string | No | Discussion 用トリアージプロンプト |

---

## Issue キュー

### GET /api/github/queue

ステータスフィルタ付きで Issue キューのアイテムを取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `status` | string | フィルタ: `pending`, `notified`, `dismissed`、または空で全件 |
| `limit` | int | 最大件数 (デフォルト 50、最大 200) |

### レスポンス

```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "repo": "owner/repo",
        "issue_number": 42,
        "title": "バグ報告タイトル",
        "body": "Issue 本文...",
        "created_at": "2026-03-15T10:00:00Z",
        "fetched_at": "2026-03-15T12:00:00Z",
        "status": "pending",
        "triage_result": "pending"
      }
    ],
    "stats": { "pending": 3, "notified": 1, "dismissed": 5, "total": 9 }
  }
}
```

### GET /api/github/queue/pending

MCP 通知用の未読 (pending) Issue を取得。

### レスポンス

```json
{
  "data": {
    "items": [...],
    "count": 3
  }
}
```

### POST /api/github/queue/<queue_id>/triage

キューアイテムのトリアージ結果を設定。

### リクエスト

```json
{ "result": "valid" }
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `result` | string | Yes | `valid` または `invalid` |

### POST /api/github/queue/<queue_id>/dismiss

キューアイテムを却下。オプションで GitHub 上の Issue を自動クローズ。

### リクエスト

```json
{
  "auto_close": true,
  "account_label": "my-account"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `auto_close` | boolean | No | GitHub 上の Issue をテンプレートコメント付きでクローズ |
| `account_label` | string | No | `auto_close` が true の場合は必須 |

### PUT /api/github/queue/<queue_id>/status

キューアイテムのステータスを更新。

### リクエスト

```json
{ "status": "notified" }
```

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `status` | string | Yes | `pending`, `notified`, または `dismissed` |

### GET /api/github/queue/config

Issue キューの設定を取得。

### レスポンス

```json
{
  "data": {
    "poll_interval_minutes": 60,
    "auto_close_invalid": false,
    "notify_on_connect": true
  }
}
```

### PUT /api/github/queue/config

Issue キューの設定を更新。

### リクエスト

```json
{
  "poll_interval_minutes": 30,
  "auto_close_invalid": true,
  "notify_on_connect": true
}
```

### POST /api/github/queue/poll

全アカウントの新規 Issue を即時ポーリング。

---

## WebUI

### GET /ext/github

GitHub Integration の WebUI ページ。ブラウザで直接アクセスする。

PIN 認証済みセッションが必要。
