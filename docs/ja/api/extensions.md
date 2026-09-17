# Extensions API

Extension の管理、インストール、セキュリティ、オーサリングに関する API。

---

## GET /api/extensions

インストール済み Extension の一覧を取得。

### パラメータ

なし

### レスポンス

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `extensions` | array | Extension 情報の配列 |
| `total` | int | Extension の総数 |
| `category_order` | string[] | カテゴリの表示順序 |

## GET /api/extensions/\<name\>

指定した Extension の詳細情報を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### エラー

- `404` — Extension が見つからない

## POST /api/extensions/\<name\>/toggle

Extension の有効/無効を切り替え。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### リクエスト

```json
{
  "enabled": true
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `enabled` | boolean | いいえ | `true` で有効化、`false` で無効化。省略時はトグル（現在の状態を反転） |

### レスポンス

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### エラー

- `404` — Extension が見つからない

## GET /api/extensions/\<name\>/config

Extension の設定スキーマと現在値を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### エラー

- `404` — Extension が見つからない

## POST /api/extensions/\<name\>/config

Extension の設定値を保存。バリデーション付き。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### リクエスト

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `values` | object | はい | フィールドキーと値のマップ |

### レスポンス

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### エラー

- `404` — Extension が見つからない
- `400` — バリデーションエラー

---

## Extension のインストール・更新・削除

以下のエンドポイントは **localhost からのアクセスのみ** 許可される。リモートからのリクエストは `403` を返す。

## POST /api/extensions/install

Git リポジトリから Extension をインストール。

### レート制限

WRITE

### アクセス制限

localhost のみ

### リクエスト

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | Git リポジトリの URL。`git`, `repo` も別名として使用可 |

### レスポンス

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### エラー

- `400` — URL が未指定、または不正な URL 形式
- `403` — localhost 以外からのアクセス

## POST /api/extensions/\<name\>/update

指定した Extension を最新版に更新 (git pull)。

### レート制限

WRITE

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### エラー

- `403` — localhost 以外からのアクセス
- `404` — Extension が見つからない

## POST /api/extensions/update-all

Git でインストールされた全 Extension を一括更新。

### レート制限

WRITE

### アクセス制限

localhost のみ

### レスポンス

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### エラー

- `403` — localhost 以外からのアクセス

## DELETE /api/extensions/\<name\>/uninstall

Extension をアンインストール（ディレクトリ削除）。

### レート制限

DESTRUCTIVE

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### エラー

- `403` — localhost 以外からのアクセス
- `404` — Extension が見つからない

---

## セキュリティ・パーミッション

## GET /api/extensions/\<name\>/permissions

Extension のパーミッション情報と承認状態を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `trust_level` | string | 信頼レベル (`trusted`, `L1`, `L2`) |
| `approved` | boolean | ユーザーによる承認済みかどうか |
| `permissions.required` | array | 必須パーミッションのリスト |
| `permissions.optional` | array | オプションパーミッションのリスト |
| `granted` | object/null | 承認済みパーミッションの詳細。未承認の場合は `null` |

### エラー

- `404` — Extension が見つからない

## POST /api/extensions/\<name\>/permissions

Extension のパーミッションを承認または取り消し。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### リクエスト（承認）

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### リクエスト（取り消し）

```json
{
  "action": "revoke"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `action` | string | いいえ | `"approve"` (デフォルト) または `"revoke"` |
| `granted` | string[] | いいえ | 承認するパーミッション名のリスト（approve 時） |
| `denied` | string[] | いいえ | 拒否するパーミッション名のリスト（approve 時） |

### レスポンス（承認時）

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### レスポンス（取り消し時）

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### エラー

- `400` — `granted` がリストでない
- `404` — Extension が見つからない

## GET /api/extensions/\<name\>/scan-results

Extension コードの静的解析結果を取得。ManifestAuthority と CodeVerifier の両方の結果を返す。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `manifest_review.approved` | boolean | マニフェスト検査の合否 |
| `manifest_review.issues` | array | 問題点のリスト (`severity`, `message`) |
| `code_scan` | object/null | コードスキャン結果。ディレクトリがない場合は `null` |
| `code_scan.findings` | array | 検出事項のリスト |

### エラー

- `404` — Extension が見つからない

## POST /api/extensions/\<name\>/rescan

Extension コードを再スキャン。`scan-results` と同じ結果を返す。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

`GET /api/extensions/<name>/scan-results` と同一形式。

## GET /api/extensions/\<name\>/tokens

Extension に発行されたケーパビリティトークンの状態を取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### エラー

- `404` — Extension が見つからない

## GET /api/extensions/\<name\>/integrity

Extension のファイル整合性ステータスを取得。取り消しトラッカーとインポートガードの情報も含む。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `integrity` | object | ファイル整合性チェックの結果 |
| `revocation` | object | トークン取り消しトラッカーの情報 |
| `import_guard` | object | インポートガードの拒否カウント |

### エラー

- `404` — Extension が見つからない

---

## フック・マーケットプレイス

## GET /api/extensions/hooks

登録済み Extension フックの一覧とフック定義を取得。

### パラメータ

なし

### レスポンス

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `hooks` | object | フック名をキーとして、登録済み Extension のリスト |
| `definitions` | object | 利用可能なフック定義。`mode` は実行モード |

## GET /api/extensions/marketplace

マーケットプレイスの Extension を検索。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `q` | string | いいえ | 検索クエリ (クエリパラメータ)。空文字で全件取得 |

### レスポンス

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `extensions` | array | マーケットプレイスの Extension 情報 |
| `extensions[].installed` | boolean | ローカルにインストール済みかどうか |
| `total` | int | 検索結果の総数 |

## POST /api/extensions/marketplace/refresh

マーケットプレイスのキャッシュを強制更新。

### レート制限

WRITE

### レスポンス

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## アイソレーション

## GET /api/extensions/isolation

プロセスアイソレーションの状態を取得。

### パラメータ

なし

### レスポンス

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `available` | boolean | プロセスアイソレーション機能が利用可能かどうか |
| `processes` | object | Extension 名をキーとしたプロセス状態のマップ |

## GET /api/extensions/os-isolation

OS レベルのアイソレーション状態を取得（Phase D）。プロセスアイソレーション情報も含む。

### パラメータ

なし

### レスポンス

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `os_isolation` | object | OS レベルのアイソレーション情報 |
| `config.enabled` | boolean | OS アイソレーションが有効かどうか |
| `config.apparmor` | boolean | AppArmor (Linux) の使用状態 |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec の使用状態 |
| `config.macos_user_isolation` | boolean | macOS ユーザー分離の使用状態 |
| `config.windows_restricted_token` | boolean | Windows 制限トークンの使用状態 |
| `config.windows_job_object` | boolean | Windows Job Object の使用状態 |
| `processes` | object | プロセスアイソレーションの状態 |

---

## Extension オーサリング

カスタム Extension の作成・編集 API。コンセッションモデルに基づき、`extensions/custom-{name}/` ディレクトリのみが書き込み対象となる。

全エンドポイントが **localhost からのアクセスのみ** 許可される。

### セキュリティ制約

- Extension 名: 小文字英数字とハイフンのみ (`[a-z0-9-]`)、最大 50 文字、`builtin-` プレフィックス禁止
- ファイルタイプ: ホワイトリスト制 (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- バイナリファイル: 完全禁止
- ファイルサイズ上限: タイプにより 10KB〜50KB

## POST /api/extensions/author/create

新しいカスタム Extension のスキャフォールドを作成。

### レート制限

WRITE

### アクセス制限

localhost のみ

### リクエスト

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `name` | string | はい | Extension 名 (`[a-z0-9-]`、最大 50 文字) |
| `description` | string | いいえ | Extension の説明文 |

### レスポンス

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### エラー

- `400` — 名前が不正、または既に存在する
- `403` — localhost 以外からのアクセス

## POST /api/extensions/author/\<name\>/write

カスタム Extension にファイルを書き込み。

### レート制限

WRITE

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ、`custom-` プレフィックスなし) |

### リクエスト

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_type` | string | はい | ファイル種別。`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` のいずれか |
| `filename` | string | はい | ファイル名（拡張子なし）。英数字・ハイフン・アンダースコアのみ |
| `content` | string | はい | ファイル内容（テキストのみ） |

### ファイルタイプ別の制約

| file_type | 拡張子 | サイズ上限 | 備考 |
|-----------|--------|-----------|------|
| `entrypoint` | `.py` | 50KB | Extension エントリポイント |
| `template` | `.html` | 50KB | `templates/{name}/` に配置 |
| `static_css` | `.css` | 50KB | `static/` に配置 |
| `static_js` | `.js` | 50KB | `static/` に配置 |
| `config` | `.json` | 10KB | ファイル名は `extension` 固定 |
| `readme` | `.md` | 20KB | ファイル名は `README` 固定 |

### レスポンス

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### エラー

- `400` — バリデーションエラー（不正な名前、ファイルタイプ、サイズ超過、バイナリ検出）
- `403` — localhost 以外からのアクセス

## GET /api/extensions/author/\<name\>/read

カスタム Extension のファイルを読み取り。

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### クエリパラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `file_type` | string | はい | ファイル種別 |
| `filename` | string | はい | ファイル名（拡張子なし） |

### レスポンス

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### エラー

- `400` — バリデーションエラー
- `403` — localhost 以外からのアクセス

## GET /api/extensions/author/\<name\>/files

カスタム Extension 内の全ファイル一覧を取得。

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### エラー

- `400` — 不正な Extension 名
- `403` — localhost 以外からのアクセス

## POST /api/extensions/author/\<name\>/validate

カスタム Extension の extension.json と コードを検証。登録せずに CodeVerifier を実行する。

### レート制限

WRITE

### アクセス制限

localhost のみ

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | Extension 名 (パスパラメータ) |

### レスポンス（成功時）

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### レスポンス（問題検出時）

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `ok` | boolean | 全検査に合格したかどうか |
| `issues` | string[] | マニフェスト検査とコード検証の問題点 |
| `code_findings` | array | CodeVerifier の検出事項 |
| `manifest` | object | パースされた extension.json の内容 |

### エラー

- `400` — 不正な Extension 名、または Extension が存在しない
- `403` — localhost 以外からのアクセス
