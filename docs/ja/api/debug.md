# Debug API

デバッグ・診断用の内部 API。ファイルメタデータの検査、モデル情報の確認、スキャン済みルートディレクトリの管理を行う。

フロントエンド UI は持たず、主に開発・トラブルシューティング用途で使用する。

## GET /api/debug/file-meta/<file_id>

ファイルのメタデータ詳細を検査する。DB に保存されたメタデータと、ZIP 内ファイルの場合は新規抽出結果も返す。

### 認証

PIN セッション または API キー

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `file_id` | int | ファイル ID（パスパラメータ） |

### レスポンス

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `id` | int | ファイル ID |
| `path` | string | ファイルパス |
| `meta_source` | string | メタデータソース（`a1111_png`, `novelai_v4_png` 等） |
| `parser_version` | int | パーサーバージョン |
| `format` | string | テンプレートフォーマット |
| `model_name` | string/null | モデル名 |
| `raw_prompt_length` | int | 生プロンプトの文字数 |
| `raw_prompt_preview` | string | 生プロンプトの先頭300文字 |
| `raw_negative_preview` | string | ネガティブプロンプトの先頭300文字 |
| `raw_meta_json_length` | int | 生メタデータ JSON の文字数 |
| `raw_meta_json_preview` | string | 生メタデータ JSON の先頭500文字 |
| `has_v4_prompt` | bool | NovelAI V4 プロンプトを含むか |
| `has_comment` | bool | Comment フィールドを含むか |

ZIP 内ファイルの場合、`fresh_extract` フィールドに再抽出結果が追加される:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### エラー

| ステータス | 説明 |
|-----------|------|
| 404 | ファイルが見つからない |

## GET /api/debug/model-check

テンプレートテーブルの `model_name` 格納状況を確認する。モデル名が設定されているレコードと未設定のレコードの統計およびサンプルを返す。

### 認証

PIN セッション または API キー

### パラメータ

なし

### レスポンス

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `total_templates` | int | テンプレートの総数 |
| `with_model_name` | int | モデル名が設定されているレコード数 |
| `without_model_name` | int | モデル名が未設定のレコード数 |
| `samples_with_model` | array | モデル名ありのサンプル（最大10件） |
| `samples_without_model` | array | モデル名なしのサンプル（最大5件） |

## GET /api/scanned-roots

DB に登録されたファイルからルートディレクトリを抽出し、ファイル数と共に返す。設定済みのスキャンルートと、それに属さないファイルのルートを集計する。

### 認証

PIN セッション または API キー

### パラメータ

なし

### レスポンス

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `roots` | array | ルートディレクトリの配列（ファイル数降順、最大50件） |
| `roots[].path` | string | ディレクトリパス |
| `roots[].count` | int | 配下のファイル数 |

### エラー

| ステータス | 説明 |
|-----------|------|
| 500 | ルート集計に失敗 |

## POST /api/debug/query

読み取り専用の SQL クエリを実行する。`YU_DEBUG_MODE=1` 環境変数が必要で、localhost からのアクセスのみ許可される。

### レート制限

WRITE

### 認証

PIN セッション または API キー（localhost 限定 + `YU_DEBUG_MODE=1`）

### リクエスト

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `sql` | string | はい | 実行する SELECT 文 |
| `limit` | int | いいえ | 返す行数の上限（デフォルト: 100、最大: 10000） |

### 制約

- SELECT 文のみ許可（INSERT, UPDATE, DELETE 等は拒否）
- 複数ステートメント（セミコロン区切り）は不可
- 書き込み系キーワード（DROP, ALTER, CREATE 等）を含むクエリは拒否

### レスポンス

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `columns` | string[] | カラム名の配列 |
| `rows` | object[] | 結果行（各行はカラム名をキーとするオブジェクト） |
| `row_count` | int | 返された行数 |
| `truncated` | bool | `limit` で切り詰められた場合は `true` |

### エラー

| ステータス | 説明 |
|-----------|------|
| 400 | SQL が空、複数ステートメント、SELECT 以外、書き込み操作を含む、SQL 構文エラー |
| 403 | デバッグモードが無効、または localhost 以外からのアクセス |

## POST /api/scanned-roots/purge

指定パス配下の全ファイルレコードを DB から永久削除する。関連するタグ・テンプレート等のレコードもカスケード削除される。未使用タグの自動削除も実行される。

### レート制限

DESTRUCTIVE

### 認証

PIN セッション または API キー

### リクエスト

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `path` | string | はい | 削除対象のルートパス。配下の全ファイルが削除される |

### レスポンス

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `purged` | int | 削除されたファイルレコード数 |
| `path` | string | 指定されたパス |

### エラー

| ステータス | 説明 |
|-----------|------|
| 400 | パスが未指定 |
| 500 | 削除処理に失敗 |
