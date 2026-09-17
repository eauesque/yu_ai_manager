# ドラッグ&ドロップ ファイル登録

メインのライブラリ画面 (`/`) に画像・動画ファイルをドラッグ&ドロップするだけで、
設定された **Drop Inbox** ディレクトリに保存し、ライブラリに自動登録します。
通常のスキャン経路 (`scan_one`) を経由するため、メタデータ抽出・サムネイル生成・
タグ付けが通常通り実行されます。

## 動作

1. メイン画面を開いた状態で、エクスプローラや他のブラウザからファイルをドラッグ
2. ウィンドウ上にオーバーレイが表示され、保存先 (Drop Inbox) のパスが表示
3. ドロップすると各ファイルが Drop Inbox にコピーされ、ライブラリに登録
4. 成功件数とエラー件数がトーストで表示

## Drop Inbox の決定ロジック

Drop Inbox は以下の優先順で決定されます:

1. `config.json` の `drop_inbox_dir` (明示指定)
2. 上記未設定時: 有効な最初のスキャンルートをそのまま使用

**制約**: `drop_inbox_dir` は必ず `scan_roots` のいずれかの配下である必要があります。
外部ディレクトリを指定すると 400 エラーで拒否されます。これは scan_roots = 
source of truth というデータモデルを壊さないためです。

## 設定例

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

`drop_inbox_dir` が存在しない場合は自動作成されます (親は `scan_roots` 配下である必要あり)。

## ファイル名の競合処理

同名ファイルが既にある場合は自動で `_1`, `_2`, ... の接尾辞を付けて保存します。
既存ファイルを上書きすることはありません。

## 許可される拡張子

| カテゴリ | 拡張子 |
|---|---|
| 画像 | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| 動画 | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

アーカイブ (`.zip` / `.7z` / `.rar`) は **D&D の対象外** です。アーカイブは通常の
スキャンルートに直接置いてスキャンしてください。

## 制限

- 1 リクエスト合計の上限は `MAX_CONTENT_LENGTH` (デフォルト **100 MB**) です
- パストラバーサル (`..` 含みファイル名) は拒否されます
- ディレクトリ丸ごとのドロップは現時点ではサポートしていません (個別ファイルのみ)

## HTTP API

### `POST /api/dnd-upload`

multipart で複数ファイルを受け取り、Drop Inbox に保存してライブラリ登録します。

レスポンス例:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

現在解決された Drop Inbox 情報を返します。UI のオーバーレイ表示に利用。

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

既にディスク上にあるファイルをパス指定で登録します (アップロードは不要)。
パスは `scan_roots` 配下である必要があります。MCP ツール `register_file` から
も利用します。

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## MCP ツール

| ツール名 | 説明 |
|---|---|
| `register_file(path)` | 絶対パスのファイルをライブラリに登録 |
| `drop_inbox_info()` | 解決された Drop Inbox ディレクトリを取得 |
