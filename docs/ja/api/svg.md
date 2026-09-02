# SVG ラスタライズ API

SVG ベクター画像を PNG/WebP ビットマップに変換する API です。
img2img パイプラインとの連携を想定しており、返却される base64 画像データを NovelAI Bridge や SD WebUI Bridge にそのまま渡せます。

## GET /api/svg/info

SVG ラスタライズ機能の利用可否を確認します。

- **Rate limit**: なし (GET)

### レスポンス

```json
{
  "available": true,
  "backend": "resvg"
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `available` | bool | ラスタライズ可能か |
| `backend` | string \| null | 使用中のバックエンド (`"resvg"` or `null`) |

---

## POST /api/svg/rasterize

SVG をラスタライズして PNG/WebP ビットマップを返します。

- **Rate limit**: HEAVY

### リクエストボディ

| パラメータ | 型 | 必須 | 説明 |
|------------|------|------|------|
| `file_id` | int | ※1 | DB 内の SVG ファイル ID |
| `svg_path` | string | ※1 | SVG ファイルの絶対パス |
| `svg_data` | string | ※1 | インライン SVG 文字列 |
| `width` | int | いいえ | 出力幅 (デフォルト: 1024) |
| `height` | int | いいえ | 出力高さ (デフォルト: 1024) |
| `format` | string | いいえ | `"png"` or `"webp"` (デフォルト: `"png"`) |
| `background` | string | いいえ | 背景色 (例: `"#ffffff"`)。未指定で透明 |

> ※1: `file_id`、`svg_path`、`svg_data` のいずれか1つを指定してください。

### リクエスト例

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### レスポンス

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| フィールド | 型 | 説明 |
|------------|------|------|
| `ok` | bool | 成功フラグ |
| `base64` | string | PNG/WebP の base64 エンコードデータ |
| `width` | int | 実際の出力幅 |
| `height` | int | 実際の出力高さ |
| `format` | string | 出力形式 |
| `size_bytes` | int | バイナリサイズ (bytes) |

### エラーレスポンス

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## MCP ツールとの連携

Claude Desktop から SVG → img2img のパイプラインを実現できます。

```
# Step 1: SVG をラスタライズ
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Step 2: 返却された base64 を img2img に渡す
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP ツール一覧

| ツール | 説明 |
|--------|------|
| `svg_info` | ラスタライズ機能の利用可否を確認 |
| `svg_rasterize` | SVG → PNG/WebP ラスタライズ |

---

## 依存パッケージ

| パッケージ | ライセンス | 用途 |
|------------|------------|------|
| `resvg` | MIT | Rust ベース SVG レンダラー (クロスプラットフォーム) |

`resvg` が未インストールの場合、サムネイルはプレースホルダー表示、API は HTTP 501 を返します。

```bash
pip install resvg
```
