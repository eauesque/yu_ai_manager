# システムアップデート API

GitHub 上の新バージョン確認とアプリケーション更新を行う API です。
インストール方式 (git / tauri / docker / portable) を自動判別し、適切な更新方法を提供します。

## GET /api/system/update/check

GitHub リポジトリから新バージョンが利用可能かチェックします。

- **Rate limit**: なし (GET)
- **認証**: PIN セッションまたは API Key

### レスポンス

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `current` | string | 現在のバージョン |
| `latest` | string | GitHub 上の最新バージョン |
| `update_available` | bool | 新バージョンが利用可能か |
| `release_url` | string | GitHub Release ページの URL |
| `release_notes` | string | リリースノート (Markdown) |
| `published_at` | string | リリース公開日時 (ISO 8601) |
| `install_type` | string | インストール方式 (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Docker 環境のみ: 更新用コマンド |
| `portable_download_url` | string \| null | Portable 環境のみ: ダウンロード URL |

---

## GET /api/system/update/status

現在のインストール方式とバージョン情報を取得します。

- **Rate limit**: なし (GET)
- **認証**: PIN セッションまたは API Key

### レスポンス

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `version` | string | 現在のバージョン |
| `install_type` | string | インストール方式 (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | 更新が進行中かどうか |

---

## POST /api/system/update/apply

利用可能な更新を適用します。git clone と portable インストールのみ対応しています。

- **Rate limit**: DESTRUCTIVE
- **認証**: PIN セッション (localhost) または再起動トークン
- **CSRF**: `X-Requested-With: XMLHttpRequest` 必須

### リクエストボディ

| パラメータ | 型 | 必須 | 説明 |
|------------|------|------|------|
| `confirm` | string | はい | 確認文字列。`"update"` を指定 |

### リクエスト例

```json
{
  "confirm": "update"
}
```

### レスポンス

```json
{
  "ok": true,
  "message": "Update started"
}
```

### SSE イベント

更新中は `update.progress` イベントが SSE で配信されます。

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `step` | string | 進行ステップ (下記参照) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | ステップの詳細情報 |

#### ステップ一覧

| ステップ | 説明 |
|----------|------|
| `backup` | バックアップ作成 |
| `fetch` | git fetch 実行 |
| `pull` | git pull 実行 |
| `download` | ファイルダウンロード (portable) |
| `extract` | アーカイブ展開 (portable) |
| `replace` | ファイル置換 (portable) |
| `pip_install` | Python 依存パッケージのインストール |
| `ts_build` | TypeScript ビルド |
| `complete` | 更新完了 |

### エラーレスポンス

**Docker 環境の場合** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Tauri 環境の場合** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## 注意事項

- Docker 環境では `/api/system/update/apply` は使用できません。`docker pull` で最新イメージを取得してください
- Tauri デスクトップアプリの更新はアプリ内蔵のアップデーターが処理します
- git / portable インストールのみ Web UI からの更新に対応しています
- 更新中はサーバーの再起動が発生する場合があります

---

## GET /api/system/update/unified-check

システム本体と全 Extension の更新状態を一括チェックします。

- **Rate limit**: なし (GET)
- **認証**: PIN セッションまたは API Key

### クエリパラメータ

| パラメータ | 型 | 説明 |
|------------|------|------|
| `force` | string | `"1"` でキャッシュを無視して再チェック |

### レスポンス

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `system` | object | システム本体の更新情報 (`check_for_update` と同じ形式) |
| `extensions` | array | 各 Extension の更新状態 |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | 更新可能な場合、リモートとのコミット差 |
| `summary` | object | カテゴリ別の集計 |

---

## POST /api/system/update/unified-apply

システム本体と Extension を一括更新します。Extension 設定は更新前に自動バックアップされます。

- **Rate limit**: DESTRUCTIVE
- **認証**: PIN セッション (localhost) または再起動トークン
- **CSRF**: `X-Requested-With: XMLHttpRequest` 必須

### リクエストボディ

| パラメータ | 型 | 必須 | 説明 |
|------------|------|------|------|
| `update_system` | bool | いいえ | システム本体を更新するか (デフォルト: true) |
| `update_extensions` | bool | いいえ | Extension を更新するか (デフォルト: true) |
| `extension_names` | array | いいえ | 更新する Extension 名のリスト (省略時は全 git Extension) |

### リクエスト例

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### レスポンス

```json
{
  "ok": true,
  "accepted": true,
  "message": "統合更新を開始しました。進捗は SSE イベント (update.progress) で通知されます。",
  "update_system": true,
  "update_extensions": true
}
```

### SSE イベント

統合更新中は `update.progress` イベントに `"unified": true` フラグが付加されます。

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### 追加ステップ

| ステップ | 説明 |
|----------|------|
| `ext_config_backup` | Extension 設定のバックアップ |
| `ext_update_<name>` | 個別 Extension の更新 |

---

## MCP ツールとの連携

Claude Desktop からシステムアップデートを管理できます。

```
# Step 1: 新バージョンの確認
check_for_update()

# Step 2: 更新ステータスの確認
get_update_status()

# Step 3: 更新の適用 (git/portable のみ)
apply_system_update(confirm="update")

# 統合チェック: システム + 全 Extension の更新確認
check_unified_updates()

# 統合更新: システム + Extension を一括更新
apply_unified_updates(update_system=True, update_extensions=True)
```

### MCP ツール一覧

| ツール | 説明 |
|--------|------|
| `check_for_update` | GitHub で新バージョンが利用可能か確認 |
| `get_update_status` | 現在のインストール方式とバージョンを取得 |
| `apply_system_update` | 利用可能な更新を適用 (git/portable のみ) |
| `check_unified_updates` | システム + 全 Extension の更新状態を一括チェック |
| `apply_unified_updates` | システム + Extension を一括更新 (設定自動バックアップ付き) |
