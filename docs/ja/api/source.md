# Source Code Browsing API

プロジェクトのソースコードを読み取り専用で参照する API。
MCP ツールや外部 AI エージェントがコードベースを安全に閲覧・検索できるように設計されている。

## セキュリティモデル

3 層防御で安全性を確保:

### 1. パス正規化 (トラバーサル防止)

- 全パスを `os.path.realpath()` で正規化し、プロジェクトルートとの前方一致を検証
- `../../etc/passwd` や `../../../Windows/System32` のようなトラバーサル攻撃を遮断
- null byte インジェクション (`\x00`) も検出・拒否

### 2. 拡張子ホワイトリスト

読み取りを許可するファイル拡張子:

| カテゴリ | 拡張子 |
|----------|--------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| 設定 | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| ドキュメント | `.md`, `.txt`, `.rst` |
| スクリプト | `.sh`, `.bat`, `.cmd`, `.ps1` |
| その他 | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

拡張子なしファイルのうち以下は特別に許可: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. 機密ファイルブロックリスト

以下のパターンに一致するファイルは拒否:

| パターン | 理由 |
|----------|------|
| `config.json`, `config_*.json` | PIN・API Key 等の認証情報 |
| `*.env`, `.env.*` | 環境変数 (シークレット) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | 暗号鍵・証明書 |
| `credentials*`, `*token*`, `*secret*` | 認証情報 |
| `*.db`, `*.sqlite*` | データベースファイル |
| `pnpm-lock.yaml`, `package-lock.json` 等 | ロックファイル (巨大) |
| 画像・動画・フォント・モデルファイル | バイナリファイル |

### ブロックされるディレクトリ

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### 読み取り上限

| 項目 | 上限 |
|------|------|
| ファイルサイズ | 1 MB |
| 1 回の読み取り行数 | 2,000 行 |
| ツリー探索深度 | 6 |
| 検索結果数 | 50 件 |

---

## エンドポイント

### GET /api/source/tree

ディレクトリツリーを取得する。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `path` | string | `""` (ルート) | 相対パス |
| `depth` | int | `3` | 探索深度 (1-6) |

#### レスポンス

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- ディレクトリが先、ファイルが後 (名前順)
- `size` はバイト数 (ファイルのみ)
- `children` は `depth` に達すると省略される

---

### GET /api/source/read

ファイル内容を行番号付きで読み取る。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `path` | string | — (必須) | 相対ファイルパス |
| `offset` | int | `0` | 開始行 (0-based) |
| `limit` | int | `2000` | 最大行数 |

#### レスポンス

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` は `{行番号}\t{行内容}` 形式
- 長いファイルは `offset` + `limit` でページネーション

#### エラー例

```json
{
  "ok": false,
  "error": "このファイルは読み取り対象外です"
}
```

```json
{
  "ok": false,
  "error": "プロジェクトルート外へのアクセスは禁止されています"
}
```

---

### GET /api/source/search

ソースコード内をテキスト検索する。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `q` | string | — (必須) | 検索テキスト (2 文字以上) |
| `glob` | string | `""` (全ファイル) | ファイル名フィルタ (例: `*.py`) |
| `limit` | int | `30` | 最大結果数 (1-50) |

#### レスポンス

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- 大文字小文字を区別しない
- `text` は最大 200 文字に切り詰め

---

## MCP ツール

| ツール名 | 説明 | 主要パラメータ |
|----------|------|---------------|
| `source_tree` | ディレクトリツリー表示 | `path`: str = '', `depth`: int = 3 |
| `source_read` | ファイル読み取り | `path`: str (必須), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | テキスト検索 | `query`: str (必須), `glob`: str = '', `limit`: int = 30 |

### MCP での使用例

```
# プロジェクト構成を確認
source_tree(path="", depth=2)

# 特定ファイルを読む
source_read(path="core/source_core/source_browser.py")

# コード内を検索
source_search(query="def register_blueprints", glob="*.py")
```

### スコープ・レート制限

- **Scope Fence**: `read_only` スコープで使用可能 (全プリセットで許可)
- **Budget Tracker**: `read` カテゴリ (レート制限なし)
- **HITL Gate**: Level 0 (承認不要)

---

## 実装ファイル

| ファイル | 役割 |
|----------|------|
| `core/source_core/source_browser.py` | セキュリティ層 + ビジネスロジック |
| `routes/source_api.py` | Flask API エンドポイント (Blueprint) |
| `mcp_server/source_tools.py` | MCP ツール登録 |
