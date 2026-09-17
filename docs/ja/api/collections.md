# Collections API

コレクション（お気に入りグループ）の管理に関する API。

## GET /api/collections

全コレクションの一覧を取得。`sort_order` 昇順、`id` 昇順でソート。

### パラメータ

なし

### レスポンス

```json
{
  "collections": [
    {
      "id": 1,
      "name": "Favorites",
      "sort_order": 0,
      "created_at": 1709500000,
      "count": 42,
      "is_smart": false,
      "query_json": null
    }
  ]
}
```

## POST /api/collections

新しいコレクションを作成。

### レート制限

WRITE

### リクエスト

```json
{
  "name": "My Collection",
  "query_json": null
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `name` | string | はい | コレクション名 |
| `query_json` | object/null | いいえ | スマートコレクション用クエリ。省略時は通常コレクション |

### レスポンス (201)

```json
{
  "id": 2,
  "name": "My Collection",
  "is_smart": false
}
```

## PUT /api/collections/<id>

コレクション名を変更。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | コレクション ID (パスパラメータ) |

### リクエスト

```json
{
  "name": "Renamed Collection"
}
```

### レスポンス

```json
{
  "id": 2,
  "name": "Renamed Collection"
}
```

## DELETE /api/collections/<id>

コレクションを削除。コレクション内の全お気に入りエントリも同時に削除される。

デフォルトコレクション (`id=1`) は削除できない。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | コレクション ID (パスパラメータ) |

### レスポンス

```json
{
  "deleted": 2
}
```

## POST /api/collections/reorder

コレクションの並び順を変更。

### レート制限

WRITE

### リクエスト

```json
{
  "ids": [3, 1, 2]
}
```

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `ids` | int[] | コレクション ID の配列。指定順が新しい並び順になる |

### レスポンス

```json
{
  "ok": true
}
```

## POST /api/collections/<id>/batch-add

コレクションにファイルを一括追加。冪等性あり：既に追加済みのエントリはスキップされ、成功としてカウントされる。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | コレクション ID (パスパラメータ) |

### リクエスト

```json
{
  "file_ids": [1, 2, 3]
}
```

| パラメータ | 型 | 制限 | 説明 |
|-----------|------|------|------|
| `file_ids` | int[] | 最大 500 件 | 追加するファイル ID の配列 |

### レスポンス

```json
{
  "total": 3,
  "succeeded": 3,
  "failed": 0,
  "errors": []
}
```

## POST /api/collections/<id>/batch-remove

コレクションからファイルを一括削除。

### レート制限

WRITE

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | コレクション ID (パスパラメータ) |

### リクエスト

```json
{
  "file_ids": [1, 2]
}
```

| パラメータ | 型 | 制限 | 説明 |
|-----------|------|------|------|
| `file_ids` | int[] | 最大 500 件 | 削除するファイル ID の配列 |

### レスポンス

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/collections/<id>/export/csv

コレクション内のファイルを CSV 形式でエクスポート。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | コレクション ID (パスパラメータ) |

### レスポンス

- Content-Type: `text/csv; charset=utf-8`
- CSV カラム: `id`, `filename`, `folder`, `path`, `meta_source`, `mtime`, `positive`, `negative`
- コレクションが存在しない場合は 404
