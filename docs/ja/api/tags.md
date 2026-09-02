# Tags API

タグの一括設定・タグ候補の検索に関する API。

## POST /api/tags/batch-set

複数ファイルに対してタグの追加・削除を一括実行する。

### レート制限

WRITE (約 120 req/min、バースト 30)

### リクエストボディ

| フィールド | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `items` | array | はい | 操作対象のリスト (最大 500 件) |
| `items[].file_id` | int | はい | ファイル ID (正の整数) |
| `items[].add` | string[] | いいえ | 追加するタグ名のリスト |
| `items[].remove` | string[] | いいえ | 削除するタグ名のリスト |

- 各アイテムには `add` または `remove` の少なくとも一方が必要
- 存在しないタグは自動的に作成される (namespace=null)
- API 経由で追加されたタグの source は `"user"` に設定される
- ファイルとの関連が無くなった孤立タグは自動削除される

### リクエスト例

```json
{
  "items": [
    {
      "file_id": 42,
      "add": ["landscape", "sunset"],
      "remove": ["lowres"]
    }
  ]
}
```

### レスポンス

```json
{
  "total": 1,
  "succeeded": 1,
  "failed": 0,
  "errors": []
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `total` | int | 処理対象の総数 |
| `succeeded` | int | 成功した件数 |
| `failed` | int | 失敗した件数 |
| `errors` | array | エラー詳細のリスト |

### エラー

| ステータス | 説明 |
|-----------|------|
| 400 | リクエストボディが不正 (items が空、file_id が不正、add/remove が両方欠落 等) |
| 429 | レート制限超過 |

---

## GET /api/tags/suggest

入力文字列に部分一致するタグ候補を返す。オートコンプリート用。

### パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `q` | string | はい | 検索文字列 |
| `limit` | int | いいえ | 返却件数の上限 (デフォルト: 20、最大: 100) |

- 検索は大文字・小文字を区別しない (LIKE %q%)
- 結果は `file_count` の降順でソートされる
- `q` が空の場合は空配列を返す

### レスポンス

```json
{
  "data": [
    { "id": 1, "tag": "landscape", "namespace": null, "file_count": 150 },
    { "id": 2, "tag": "1girl", "namespace": null, "file_count": 3420 }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `data[].id` | int | タグ ID |
| `data[].tag` | string | タグ名 |
| `data[].namespace` | string\|null | 名前空間 (通常は null) |
| `data[].file_count` | int | このタグが付与されているファイル数 |
