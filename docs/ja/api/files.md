# Files API

ファイル詳細・サムネイル・オリジナルメディアの取得に関する API。

## GET /api/file/<id>

ファイルの詳細メタデータを取得。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | ファイル ID (パスパラメータ) |

### レスポンス

```json
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
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

サムネイル画像 (WebP)。ETag キャッシュ対応。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | ファイル ID |
| `size` | int | サムネイルサイズ (デフォルト 300) |

### レスポンス

- Content-Type: `image/webp`
- ETag / If-None-Match 対応 (304 Not Modified)
- キャッシュ: 24 時間

## GET /api/original/<id>

オリジナルファイルをストリーム配信。ZIP 内ファイルにも対応。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `id` | int | ファイル ID |

### レスポンス

- Content-Type: ファイルの MIME タイプ
- Content-Disposition: `inline`
- Range リクエスト対応 (動画シーク用)

## POST /api/convert

プロンプト形式変換 (A1111 <-> NAI)。

### リクエスト

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### レスポンス

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

コンテナ (フォルダ/ZIP) のサムネイル ID 一覧 (未キャッシュ分)。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `keys` | string | コンテナキー (カンマ区切り) |
