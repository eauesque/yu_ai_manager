# Search API

ファイル検索・サジェスト・グループ表示に関する API。

## GET /api/search

メインのファイル検索エンドポイント。

### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `q` | string | `""` | 検索クエリ (プロンプト内テキスト、タグ名) |
| `sort` | string | `"date"` | ソート順: `date`, `name`, `size`, `rating`, `random` |
| `order` | string | `"desc"` | `asc` / `desc` |
| `offset` | int | `0` | ページネーション開始位置 |
| `limit` | int | `50` | 取得件数 (最大 200) |
| `cursor` | string | - | カーソルベースページネーション用トークン |
| `meta` | string | `"all"` | メタデータ種別: `all`, `a1111`, `nai`, `comfy`, `unknown` |
| `tags` | string | - | タグフィルタ (カンマ区切り) |
| `rating_min` | int | - | 最小レーティング (0-5) |
| `rating_max` | int | - | 最大レーティング (0-5) |
| `path` | string | - | パス前方一致フィルタ |
| `ext` | string | - | 拡張子フィルタ (カンマ区切り、例: `png,webp`) |
| `has_prompt` | bool | - | プロンプト有無フィルタ |
| `collection_id` | int | - | コレクション内検索 |
| `favorites_only` | bool | `false` | お気に入りのみ |
| `group_by` | string | - | グルーピング: `folder`, `conversation` |

### レスポンス

```json
{
  "results": [
    {
      "id": 42,
      "path": "/images/output/00042.png",
      "filename": "00042.png",
      "size": 1234567,
      "mtime": 1709500000,
      "width": 1024,
      "height": 1536,
      "meta_type": "a1111_png",
      "model_name": "animagine-xl-3.1",
      "positive": "1girl, landscape, sunset",
      "negative": "low quality",
      "rating": 4,
      "is_favorite": true,
      "tags": ["landscape", "sunset"]
    }
  ],
  "total": 1500,
  "offset": 0,
  "limit": 50,
  "next_cursor": "eyJtdGltZSI6MTcwOTUwMDAwMCwiaWQiOjQyfQ=="
}
```

## GET /api/search-grouped

フォルダ/ZIP 単位でグルーピングした検索結果。

### パラメータ

`/api/search` と同じクエリパラメータに加え:

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `group_limit` | int | グループ内の最大表示件数 |

## GET /api/groups-index

フォルダ・ZIP コンテナのインデックス一覧。検索結果のグループ化に使用。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `sort` | string | ソート順: `name`, `count`, `date` |
| `order` | string | `asc` / `desc` |
| `offset` | int | ページネーション開始位置 |
| `limit` | int | 取得件数 |

## GET /api/group-members

指定コンテナ内のファイル ID 一覧。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `key` | string | コンテナキー (フォルダパスまたは ZIP パス) |

## GET /api/suggest

タグ・プロンプトのオートコンプリート。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `q` | string | 入力テキスト |
| `limit` | int | 候補数 (デフォルト 10) |

### レスポンス

```json
{
  "suggestions": [
    { "value": "1girl", "count": 5432 },
    { "value": "1boy", "count": 1234 }
  ]
}
```

## GET /api/suggest/lora

LoRA モデル名のサジェスト。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `q` | string | 入力テキスト |
| `limit` | int | 候補数 |

## GET /api/server-info

サーバー基本情報。

### レスポンス

```json
{
  "version": "4.12.1",
  "db_path": "/path/to/tags.db",
  "file_count": 150000,
  "tag_count": 8500,
  "auth_required": false,
  "lan_ip": "192.168.1.100",
  "active_ui": "default"
}
```
