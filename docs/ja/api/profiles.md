# Profiles API

設定プロファイルの管理に関する API。プロファイルはアプリケーション設定の名前付きスナップショットで、`profiles/<name>.json` に保存される。

全エンドポイントは PIN 認証が必要。PIN 認証が無効、またはセッション未認証の場合は 403 / 401 を返す。

## プロファイル名のルール

- 1〜64 文字
- 使用可能文字: `a-zA-Z0-9_-`

---

## GET /api/profiles

全プロファイルのメタデータ一覧を取得。お気に入り優先、次にラベルのアルファベット順でソート。

### パラメータ

なし

### レスポンス

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (ファイル名に使用) |
| `label` | string | 表示用ラベル |
| `description` | string | 説明文 |
| `favorite` | boolean | お気に入りフラグ |
| `last_used_at` | string/null | 最終使用日時 (ISO 8601) |
| `created_at` | string/null | 作成日時 (ISO 8601) |
| `db` | string/null | 関連付けられた DB パス |
| `is_active` | boolean | 現在アクティブなプロファイルかどうか |

## GET /api/profiles/\<name\>

指定プロファイルの全データを取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (パスパラメータ) |

### レスポンス

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `invalid_profile_name` | 400 | プロファイル名が不正 |
| `profile_not_found` | 404 | プロファイルが存在しない |

## POST /api/profiles

新しいプロファイルを作成。

### レート制限

WRITE

### リクエスト

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `name` | string | はい | プロファイル名 (`a-zA-Z0-9_-`、1〜64 文字) |
| `label` | string | いいえ | 表示用ラベル。省略時は `name` を使用 |
| `description` | string | いいえ | 説明文 |
| `base_config` | object | いいえ | 初期設定値。メタデータキー (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) 以外のキーがプロファイルにコピーされる |

### レスポンス (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `invalid_profile_name` | 400 | プロファイル名が不正 |
| `invalid_label` | 400 | ラベルが空 |
| `profile_exists` | 409 | 同名のプロファイルが既に存在する |

## PUT /api/profiles/\<name\>

プロファイルのメタデータを更新。`label`、`description`、`favorite` のみ変更可能。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (パスパラメータ) |

### リクエスト

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `label` | string | いいえ | 表示用ラベル |
| `description` | string | いいえ | 説明文 |
| `favorite` | boolean | いいえ | お気に入りフラグ |

少なくとも 1 つのフィールドが必要。

### レスポンス

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `empty_update` | 400 | 更新フィールドが指定されていない |
| `update_failed` | 400 | プロファイルが存在しない等 |

## DELETE /api/profiles/\<name\>

プロファイルを削除。現在アクティブなプロファイルは削除できない。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (パスパラメータ) |

### レスポンス

```json
{
  "deleted": "my_profile"
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `delete_active` | 400 | アクティブプロファイルは削除できない |
| `delete_failed` | 400 | プロファイルが存在しない等 |

## POST /api/profiles/\<name\>/duplicate

プロファイルを複製して新しい名前で保存。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | コピー元プロファイル名 (パスパラメータ) |

### リクエスト

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `new_name` | string | はい | 新しいプロファイル名 |
| `new_label` | string | いいえ | 新しい表示用ラベル。省略時は `new_name` を使用 |

### レスポンス (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `duplicate_failed` | 400 | コピー元が存在しない、新しい名前が不正、同名が既に存在する |

## POST /api/profiles/\<name\>/rename

プロファイルをリネーム。アクティブプロファイルの場合は `config.json` の `active_profile` も自動更新される。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | 現在のプロファイル名 (パスパラメータ) |

### リクエスト

```json
{
  "new_name": "renamed_profile"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `new_name` | string | はい | 新しいプロファイル名 |

### レスポンス

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `invalid_profile_name` | 400 | 新しいプロファイル名が不正 |
| `rename_failed` | 400 | 元のプロファイルが存在しない、新しい名前が既に存在する |

## POST /api/profiles/\<name\>/favorite

プロファイルのお気に入り状態をトグル。現在の `favorite` 値を反転させる。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (パスパラメータ) |

### リクエスト

ボディ不要。

### レスポンス

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `profile_not_found` | 404 | プロファイルが存在しない |
| `favorite_failed` | 400 | 更新に失敗 |

---

## QR エクスポート / インポート

プロファイルを QR コード用の JSON 文字列としてエクスポート・インポートする機能。機密情報 (`pin`, `token`, `secret`, `key` を含むフィールド) はエクスポート時に自動的に除外される。

## GET /api/profiles/\<name\>/export

プロファイルを QR コード用 JSON としてエクスポート。機密フィールドは除外される。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | プロファイル名 (パスパラメータ) |

### レスポンス

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` は QR コードに埋め込むための JSON 文字列。`schema` フィールドでフォーマットバージョンを識別する。

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `profile_not_found` | 404 | プロファイルが存在しない |

## POST /api/profiles/import-preview

QR データからのインポートをプレビュー。既存プロファイルとの差分確認に使用する。実際のインポートは行わない。

### レート制限

WRITE

### リクエスト

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `qr_data` | string/object | はい | QR コードから読み取った JSON 文字列またはパース済みオブジェクト |

### レスポンス (新規プロファイルの場合)

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### レスポンス (既存プロファイルの場合)

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `invalid_qr` | 400 | QR データが不正、または `profile` キーが含まれていない |
| `invalid_profile_name` | 400 | プロファイル名が不正 |

## POST /api/profiles/import

QR データからプロファイルをインポート。新規作成、差分マージ、完全上書きの 3 モードをサポート。

### レート制限

WRITE

### リクエスト

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `qr_data` | string/object | はい | QR コードから読み取った JSON 文字列またはパース済みオブジェクト |
| `mode` | string | いいえ | インポートモード: `full` (完全上書き、デフォルト), `diff` (差分マージ), `new` (新規のみ) |

### レスポンス

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

新規作成時はステータス 201 を返す。

### エラー

| コード | 状態 | 説明 |
|--------|------|------|
| `invalid_qr` | 400 | QR データが不正 |
| `invalid_profile_name` | 400 | プロファイル名が不正 |
| `profile_exists` | 409 | `mode=new` で同名プロファイルが既に存在する |
| `import_failed` | 400 | インポートに失敗 |
