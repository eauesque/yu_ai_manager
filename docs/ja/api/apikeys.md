# API Keys API

API キーの作成・一覧取得・削除を行う API。全エンドポイントで PIN セッション認証が必要。

API キーは `sk_` + 32桁の16進数（128ビット）形式で生成される。サーバー側にはハッシュのみが保存され、生のキーは作成時に一度だけ返される。

## スコープ

API キーにはスコープを設定でき、アクセス可能なエンドポイントを制限できる。スコープを省略した場合は読み取り専用アクセスとなる。

| スコープ | 説明 |
|---------|------|
| `read` | 検索、ファイル詳細、サムネイル、統計 |
| `rate` | レーティングの取得・設定・一括操作 |
| `tag.write` | タグの追加・削除 |
| `collection.write` | コレクション作成・更新・削除、お気に入り操作 |
| `annotate` | アノテーションの読み書き・削除 |
| `scan` | スキャンの開始・キャンセル・再開 |
| `admin` | API キー管理、設定、バックアップ・リストア |

## POST /api/apikeys

新しい API キーを作成する。

### レート制限

WRITE（スコープ: `admin`）

### 認証

PIN セッション または `admin` スコープを持つ API キー

### リクエスト

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `label` | string | いいえ | キーの識別ラベル。省略時は `Key <timestamp>` が自動設定 |
| `scopes` | string[] | いいえ | スコープの配列。省略または空配列の場合は読み取り専用 |

### レスポンス (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **注意**: `key` フィールドは作成時のレスポンスにのみ含まれる。この値は二度と取得できないため、必ず安全な場所に保存すること。

### エラー

| ステータス | 説明 |
|-----------|------|
| 400 | 無効なスコープが指定された |

## GET /api/apikeys

全 API キーの一覧を取得する。ハッシュは含まれず、プレフィックスのみ返される。

### 認証

PIN セッション または API キー（`admin` スコープ）

### パラメータ

なし

### レスポンス

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `id` | string | キー ID（`ak_` プレフィックス） |
| `key_prefix` | string | キーの先頭10文字（識別用） |
| `label` | string | ユーザー設定のラベル |
| `created_at` | int | 作成日時（Unix タイムスタンプ） |
| `last_used_at` | int/null | 最終使用日時。未使用の場合は `null` |
| `scopes` | string[] | 設定されたスコープ。未設定の場合はフィールド自体が省略される |

## DELETE /api/apikeys/<key_id>

API キーを削除（無効化）する。

### レート制限

WRITE（スコープ: `admin`）

### 認証

PIN セッション または `admin` スコープを持つ API キー

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key_id` | string | API キー ID（パスパラメータ） |

### レスポンス

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### エラー

| ステータス | 説明 |
|-----------|------|
| 404 | 指定された ID のキーが見つからない |

## API キーの使用方法

作成した API キーは `Authorization` ヘッダで使用する:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

API キーを使用したリクエストでは CSRF ヘッダ (`X-Requested-With`) は不要。
