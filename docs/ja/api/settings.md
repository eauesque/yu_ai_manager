# Settings API

アプリケーション設定の取得・更新、シークレット管理、外部パスワードマネージャー (1Password / Bitwarden) との連携に関する API。

シークレット値は全ての GET レスポンスでマスクされる (`****` 形式)。各設定値がどのバックエンドから取得されたかは `source` フィールドで判別できる。

## 認証

全エンドポイントに PIN 認証またはAPI Key 認証が必要。

---

## GET /api/settings/schema

設定スキーマの全定義を取得。各設定項目のキー名・型・デフォルト値・カテゴリ等の定義情報を返す。

### パラメータ

なし

### レスポンス

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー (ドット区切り、例: `github.token`) |
| `type` | string | 値の型 (`str`, `int`, `float`, `bool`) |
| `default` | any | デフォルト値 |
| `category` | string | カテゴリ名 |
| `secret` | bool | シークレット値かどうか |
| `label` | string | 表示用ラベル |

---

## GET /api/settings/all

全設定値を一覧取得。シークレット値はマスクされた状態で返される。

### パラメータ

なし

### レスポンス

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー |
| `value` | any | 現在の値 (シークレットはマスク済み) |
| `source` | string | 値の取得元。`default` / `config` / `encrypted` / `1password` / `bitwarden` のいずれか |
| `secret` | bool | シークレット値かどうか |
| `category` | string | カテゴリ名 |

---

## GET /api/settings/\<key\>

単一の設定値を取得。キーはドット区切りのパス形式 (例: `github.token`)。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー (パスパラメータ) |

### レスポンス

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 404 | `not_found` | 未定義の設定キー |

---

## PUT /api/settings/\<key\>

設定値を更新する。シークレット値は自動的に暗号化される。1Password URI を指定してシークレットを外部管理にすることも可能。

### レート制限

DESTRUCTIVE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー (パスパラメータ) |

### リクエスト

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `value` | any | はい | 設定する値。スキーマの型定義に従い自動変換される |
| `op_uri` | string | いいえ | 1Password URI。指定すると値の代わりに `op_secrets` マッピングが保存される |

### レスポンス

```json
{
  "key": "github.token",
  "updated": true
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `bad_request` | リクエストボディに `value` がない |
| 404 | `not_found` | 未定義の設定キー |

---

## GET /api/settings/secrets/status

暗号化キーのバックエンド状態を取得。現在どの鍵管理方式が使用されているかを返す。

### パラメータ

なし

### レスポンス

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `backend` | string | 現在の鍵バックエンド (`keychain` / `passphrase` / `file`) |
| `available` | bool | 暗号化機能が利用可能か |
| `keychain_supported` | bool | OS キーチェーンがサポートされているか |

---

## POST /api/settings/secrets/export

暗号化キーをパスワード保護された JSON として書き出す。バックアップや別環境への移行に使用。

### レート制限

DESTRUCTIVE

### リクエスト

```json
{
  "password": "my-export-password"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `password` | string | はい | エクスポートデータを保護するパスワード |

### レスポンス

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `bad_request` | リクエストボディに `password` がない |
| 400 | `export_failed` | エクスポート処理に失敗 |

---

## POST /api/settings/secrets/import

エクスポートされた暗号化キーをインポートする。

### レート制限

DESTRUCTIVE

### リクエスト

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `export_data` | string | はい | エクスポート時に取得したデータ |
| `password` | string | はい | エクスポート時に設定したパスワード |

### レスポンス

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `bad_request` | `export_data` または `password` が不足 |
| 400 | `import_failed` | パスワードが不正、またはデータが破損 |

---

## POST /api/settings/secrets/migrate-keychain

暗号化キーをファイルバックエンドから OS キーチェーンに移行する。macOS Keychain / Windows Credential Manager / Linux Secret Service に対応。

### レート制限

DESTRUCTIVE

### リクエスト

なし (ボディ不要)

### レスポンス

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `migration_failed` | キーチェーンが利用不可、または移行に失敗 |

---

## GET /api/settings/op-status

1Password CLI (`op`) の接続状態を取得。

### パラメータ

なし

### レスポンス

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `available` | bool | `op` コマンドが PATH 上に存在するか |
| `signed_in` | bool | 1Password にサインイン済みか |
| `version` | string | `op` CLI のバージョン |

---

## GET /api/settings/secrets/op-vaults

1Password で利用可能な Vault 一覧を取得。

### パラメータ

なし

### レスポンス

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 503 | `op_unavailable` | 1Password CLI が利用できない |

---

## POST /api/settings/secrets/push-to-op

全シークレット設定値を 1Password にバッチ書き込みし、`op_secrets` マッピングを config.json に保存する。

### レート制限

DESTRUCTIVE

### リクエスト

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `vault` | string | はい | 書き込み先の 1Password Vault 名 |
| `item_title` | string | いいえ | 1Password アイテムのタイトル。デフォルト: `YU AI Manager` |
| `remove_local` | bool | いいえ | `true` の場合、プッシュ後にローカルの暗号化値を config.json から削除。デフォルト: `false` |

### レスポンス

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `bad_request` | `vault` が未指定 |
| 400 | `no_secrets` | 書き込み対象のシークレットがない |
| 500 | `op_push_failed` | 1Password への書き込みに失敗 |
| 503 | `op_unavailable` | 1Password CLI が利用できない |

---

## DELETE /api/settings/op-mapping/\<key\>

1Password URI マッピングを削除し、ローカル暗号化にフォールバックさせる。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー (パスパラメータ) |

### レスポンス

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 404 | `not_found` | 指定キーが `op_secrets` マッピングに存在しない |

---

## GET /api/settings/bw-status

Bitwarden CLI (`bw`) の接続状態を取得。

### パラメータ

なし

### レスポンス

```json
{
  "available": true,
  "status": "unlocked"
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `available` | bool | `bw` コマンドが PATH 上に存在するか |
| `status` | string | Bitwarden のセッション状態 |

---

## GET /api/settings/secrets/bw-folders

Bitwarden で利用可能なフォルダ一覧を取得。

### パラメータ

なし

### レスポンス

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 503 | `bw_unavailable` | Bitwarden CLI が利用できない |

---

## POST /api/settings/secrets/push-to-bw

全シークレット設定値を Bitwarden にバッチ書き込みし、`bw_secrets` マッピングを config.json に保存する。

### レート制限

WRITE

### リクエスト

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `folder_id` | string/null | いいえ | 書き込み先の Bitwarden フォルダ ID。省略時はフォルダなし |
| `item_name` | string | いいえ | Bitwarden アイテム名。デフォルト: `YU AI Manager` |

### レスポンス

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 400 | `no_secrets` | 書き込み対象のシークレットがない |
| 500 | `bw_push_failed` | Bitwarden への書き込みに失敗 |
| 503 | `bw_unavailable` | Bitwarden CLI が利用できない |

---

## DELETE /api/settings/bw-mapping/\<key\>

Bitwarden マッピングを削除し、ローカル暗号化にフォールバックさせる。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key` | string | 設定キー (パスパラメータ) |

### レスポンス

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### エラー

| ステータス | コード | 説明 |
|-----------|--------|------|
| 404 | `not_found` | 指定キーが `bw_secrets` マッピングに存在しない |
