# Tools API

重複検出、ハッシュ計算、類似画像検索、キャッシュ管理、フォルダ選択、DB バックアップ、アーカイブクリーンアップ、デバッグログなどのユーティリティ API。

---

## 重複・ハッシュ・スキャン

### GET /api/tools/find-duplicates

ファイルハッシュまたはファイル名に基づいて重複ファイルを検出。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `cross_directory` | string | `"false"` | `"true"` で異なるディレクトリ間の重複も検出 |
| `method` | string | `"hash"` | 検出方法。`"hash"` または `"name"` |
| `threshold` | int | `5` | 類似度の閾値 |

#### レスポンス

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

未計算ファイルのハッシュ値をバックグラウンドで計算開始。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "type": "both",
  "limit": 5000
}
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `type` | string | `"both"` | ハッシュ種別。`"md5"`, `"sha256"`, `"both"` |
| `limit` | int | `5000` | 処理するファイル数の上限 |

#### レスポンス

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

重複グループから指定ファイルを削除。

#### レート制限

DESTRUCTIVE

#### リクエスト

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `groups` | array | 必須 | 削除対象グループ。`keep` に残すファイル ID、`delete` に削除するファイル ID 配列 |
| `mode` | string | `"soft"` | `"soft"` = 論理削除、`"hard"` = 物理削除 |

#### レスポンス

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

タグの正規化（重複タグの統合、空白トリムなど）を実行。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `dry_run` | string | `"false"` | `"true"` で実際の変更を行わずプレビュー |

#### レスポンス

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

指定ファイルに類似する画像を検索（ハッシュベース）。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_id` | int | はい | 基準ファイルの ID |
| `threshold` | int | いいえ | 類似度閾値 (1-20、デフォルト `5`) |

#### レスポンス

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### エラー

- `400` — `file_id` 未指定または無効
- `404` — 指定ファイルが見つからない

### POST /api/tools/scan

指定パスのファイルをスキャンして DB に登録。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `path` | string | 必須 | スキャン対象ディレクトリのパス |
| `recursive` | bool | `true` | サブディレクトリを再帰的にスキャン |
| `scan_zips` | bool | `false` | ZIP アーカイブ内もスキャン |
| `compute_hash` | bool | `false` | スキャン時にハッシュも計算 |

#### レスポンス

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## ファイル検索・メタデータ検査

### GET /api/tools/file-search

DB 内のファイルをキーワードで検索。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `q` / `query` | string | `""` | 検索キーワード |
| `meta` / `meta_filter` | string | `"all"` | メタデータソースでフィルタ (`"all"`, `"a1111_png"`, `"novelai_v4_png"` 等) |
| `limit` / `n` / `page_size` | int | `100` | 取得件数 (1-500) |

#### レスポンス

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

アップロードされたファイルのメタデータを検査。ファイルを DB に登録せずメタデータのみ抽出する。

#### レート制限

WRITE

#### リクエスト

`multipart/form-data` 形式:

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file` | file | はい | 検査対象のファイル |
| `zip_entry` | string | いいえ | ZIP 内エントリのパス（ZIP ファイルの場合） |

#### レスポンス

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### エラー

- `400` — ファイル未アップロード

---

## フォルダ選択・ディレクトリ一覧

### GET /api/tools/select-folder

OS ネイティブのフォルダ選択ダイアログを表示。**localhost からのみ使用可能。**

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `initial` / `path` / `dir` | string | ダイアログの初期ディレクトリ |

#### レスポンス

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

リモートアクセス時:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "リモートアクセス時はネイティブフォルダダイアログを使用できません。サーバーフォルダー参照を使ってください。"
}
```

### GET /api/tools/list-dirs

サーバー上のディレクトリ一覧を取得。**localhost からのみ使用可能。**

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `path` / `dir` / `initial` | string | 一覧を取得するディレクトリパス。空の場合はルートディレクトリ |

#### レスポンス

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### エラー

- `403` — リモートアクセス

---

## キャッシュ管理

### GET /api/tools/cache-info

サムネイルキャッシュの状態を取得。

#### レスポンス

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

サムネイルキャッシュを全削除。

#### レート制限

DESTRUCTIVE

#### レスポンス

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

グループインデックスキャッシュを強制再構築。

#### レート制限

DESTRUCTIVE

#### レスポンス

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

全 MP4/MOV ファイルの faststart キャッシュをバックグラウンドで事前生成。即座に 202 を返す。

#### レート制限

WRITE

#### レスポンス (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

既に実行中の場合 (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## 設定

### GET /api/settings/config

現在の設定をデフォルト値とマージして取得。

#### レスポンス

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

設定を部分的に更新。既存のネスト済みオブジェクトにはディープマージが適用される。

#### レート制限

DESTRUCTIVE

#### リクエスト

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### レスポンス

```json
{
  "status": "saved"
}
```

#### エラー

- `400` — データが空

---

## DB バックアップ・リストア

### GET /api/tools/backup-download

データベースファイルを直接ダウンロード。**localhost からのみ使用可能。**

#### レスポンス

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- データベースが見つからない場合は 404

### POST /api/tools/restore

アップロードした `.db` ファイルで DB を上書きリストア。**localhost からのみ使用可能。** リストア前に自動で既存 DB のバックアップを作成する。

#### レート制限

WRITE

#### リクエスト

`multipart/form-data` 形式:

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file` | file | はい | `.db` 拡張子の SQLite ファイル |

#### バリデーション

- SQLite マジックバイトの検証
- `files` テーブルの存在確認
- トリガー・ビューなどの危険なオブジェクトが含まれていないか検証

#### レスポンス

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### エラー

- `400` — ファイル未アップロード、拡張子不正、無効な SQLite
- `403` — リモートアクセス
- `500` — バックアップ/リストア失敗

### POST /api/tools/backup/create

管理されたバックアップを手動作成。**localhost からのみ使用可能。**

#### レート制限

DESTRUCTIVE

#### レスポンス

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

利用可能なバックアップの一覧を取得。

#### レスポンス

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

指定したバックアップファイル名から DB をリストア。**localhost からのみ使用可能。**

#### レート制限

DESTRUCTIVE

#### リクエスト

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `filename` | string | はい | リストア対象のバックアップファイル名 |

#### レスポンス

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### エラー

- `400` — ファイル名未指定またはバックアップが見つからない
- `403` — リモートアクセス

### POST /api/tools/backup/delete

指定したバックアップを削除。**localhost からのみ使用可能。**

#### レート制限

DESTRUCTIVE

#### リクエスト

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `filename` | string | はい | 削除対象のバックアップファイル名 |

#### レスポンス

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

バックアップシステムの状態を取得。

#### レスポンス

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## デバッグログ

### GET /api/tools/debug-log

デバッグログの末尾を取得。デバッグモードが無効の場合は `enabled: false` を返す。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `limit` | int | `200` | 取得する行数 (1-5000) |
| `filter` | string | `""` | 行フィルタ文字列（部分一致） |

#### レスポンス

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

デバッグログファイルをダウンロード。**localhost からのみ使用可能。**

#### レスポンス

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### エラー

- `400` — デバッグモード無効
- `403` — リモートアクセス
- `404` — ログファイルが存在しない

### POST /api/tools/debug-log/clear

デバッグログをクリア。**localhost からのみ使用可能。**

#### レート制限

WRITE

#### レスポンス

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### エラー

- `400` — デバッグモード無効
- `403` — リモートアクセス
- `404` — ログファイルが存在しない

---

## アーカイブクリーンアップ

展開済みアーカイブと対応フォルダの重複を検出・整理するツール。全エンドポイント **localhost からのみ使用可能。**

### POST /api/tools/archive-cleanup/scan

アーカイブと展開先フォルダのペアをスキャン。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `path` | string | 必須 | スキャン対象ディレクトリ |
| `recursive` | bool | `false` | サブディレクトリも再帰的にスキャン |

#### パスバリデーション

- `~` で始まるパスは拒否
- `..` を含むパスは拒否

#### レスポンス

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

スキャン結果に対するクリーンアップアクションを実行。

#### レート制限

DESTRUCTIVE

#### リクエスト

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `actions` | array | アクションの配列 |
| `actions[].action` | string | `"delete_archive"`, `"delete_folder"`, `"skip"` のいずれか |
| `actions[].archive_path` | string | `delete_archive` 時に必須 |
| `actions[].folder_path` | string | `delete_folder` 時に必須 |

#### レスポンス

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

LLM を使用してアーカイブ・フォルダペアの同一性を検証（単一ペア）。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `archive_path` | string | はい | アーカイブファイルのパス |
| `folder_path` | string | はい | 展開先フォルダのパス |
| `pair_info` | object | いいえ | ペアに関する追加情報 |

#### レスポンス

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

LLM を使用して複数ペアを一括検証。最大 50 ペア。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| パラメータ | 型 | 制限 | 説明 |
|-----------|------|------|------|
| `pairs` | array | 最大 50 件 | 検証対象ペアの配列 |

#### レスポンス

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

アーカイブクリーンアップ用 LLM 設定を取得。

#### レスポンス

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

アーカイブクリーンアップ用 LLM 設定を保存。

#### レート制限

WRITE

#### リクエスト

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### レスポンス

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

指定エンジンの利用可能モデル一覧を取得。

#### リクエスト

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `engine` | string | はい | `"ollama"` または `"openai_compat"` |
| `base_url` | string | はい | エンジンの API URL |
| `api_key` | string | いいえ | `openai_compat` の場合の API キー |

#### レスポンス

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### エラー

- `400` — `engine` 不正または `base_url` 未指定
