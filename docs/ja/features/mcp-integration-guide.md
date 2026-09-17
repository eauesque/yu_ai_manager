# MCP 連携ガイド — LLM から YU AI Manager を操作する

YU AI Manager は **MCP (Model Context Protocol)** サーバーを内蔵しており、
LLM アプリケーションから自然言語で画像ライブラリを操作できます。

チャット UI は本アプリには組み込まれていません。
「自然言語で何かやりたい」場合は、お好みの MCP 対応クライアントから接続してください。

---

## MCP とは

MCP (Model Context Protocol) は、LLM アプリケーションが外部ツールやデータソースに
アクセスするための標準プロトコルです。
YU AI Manager が MCP サーバーとして動作し、LLM クライアント（Claude Desktop 等）が
そこに接続することで、自然言語の指示を API 操作に変換して実行できます。

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM クライアント │ ◄──────────────────► │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline 等)    │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     ▼
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web サーバー        │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## 対応している MCP クライアント

以下は代表的な MCP 対応クライアントです。いずれも設定方法は同様です。

| クライアント | 提供元 | 特徴 |
|---|---|---|
| **Claude Desktop** | Anthropic | Claude を直接利用。MCP ネイティブ対応 |
| **Claude Code** | Anthropic | ターミナルベースの開発向けクライアント |
| **Cline** | VS Code 拡張 | エディタ統合。複数 LLM 対応 |
| **Open WebUI** | オープンソース | セルフホスト型。Ollama 等ローカル LLM と組み合わせ可能 |

※ MCP 対応クライアントは急速に増えています。
stdio トランスポートに対応していれば基本的に接続可能です。

## セットアップ

### 1. YU AI Manager を起動する

MCP サーバーは Web サーバーの API を経由して動作するため、
先に YU AI Manager 本体を起動しておく必要があります。

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. API キーを発行する（推奨）

LAN 公開・PIN 認証環境で使う場合は、API キーを発行しておくと
MCP サーバーが PIN 認証をバイパスできます。

設定画面 → API Keys から発行できます。

PIN なし（`config_test.json`）で起動している場合、API キーは不要です。

### 3. MCP クライアントに接続設定を追加する

#### Claude Desktop の場合

`claude_desktop_config.json` を編集します:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code の場合

プロジェクトルートの `.mcp.json` に記述するか、`claude mcp add` コマンドで追加します:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code) の場合

Cline の MCP Settings から同様の情報を入力します。

#### 環境変数一覧

| 変数名 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web サーバーの URL |
| `YU_API_KEY` | - | なし | API キー（PIN 環境で必要） |
| `YU_DEBUG_MODE` | - | `0` | `1` でデバッグツールを追加 |

## 使い方の例

接続が完了すると、LLM に自然言語で指示するだけで画像ライブラリを操作できます。

### 検索・閲覧

```
「青い目の女の子の画像を最新20件見せて」
「NovelAI で生成した画像だけ絞り込んで」
「先週スキャンした画像の統計を教えて」
```

### 整理・分類

```
「この10枚の画像に星5をつけて」
「"landscape" タグがついた画像を "風景コレクション" に追加して」
「rating が3以下の画像をリストアップして」
```

### 分析・アノテーション

```
「最近追加した画像の品質をスコアリングして annotations に保存して」
「画像 ID 12345 の全アノテーションを見せて」
「agent:claude ソースのアノテーションを検索して」
```

### スキャン操作

```
「新しい画像をスキャンして」
「スキャンの進捗を確認して」
「スキャンエラーがあれば見せて」
```

## 提供されるツール一覧

MCP サーバーは以下のツールを LLM に公開します:

### 検索・閲覧 (4 tools)

| ツール名 | 説明 |
|---|---|
| `search_images` | タグ・日付・形式・レーティング等で画像を検索 |
| `get_image_detail` | 画像の全メタデータを取得 |
| `get_library_stats` | ライブラリ統計（ファイル数、タグ数、ソース分布等） |
| `find_similar` | 知覚ハッシュで類似画像を検索 |

### コレクション (4 tools)

| ツール名 | 説明 |
|---|---|
| `list_collections` | コレクション一覧 |
| `create_collection` | コレクション作成 |
| `delete_collection` | コレクション削除 |
| `add_to_collection` / `remove_from_collection` | 画像の追加・削除 |

### タグ・レーティング (2 tools)

| ツール名 | 説明 |
|---|---|
| `rate_images` | 複数画像にまとめて星レーティングを設定 |
| `set_tags` | 複数画像にまとめてタグを追加・削除 |

### アノテーション (4 tools)

| ツール名 | 説明 |
|---|---|
| `set_annotations` | AI 分析結果等をアノテーションとして保存 |
| `get_annotations` | 画像のアノテーションを取得 |
| `search_annotations` | ソース・キー・信頼度でアノテーションを横断検索 |
| `delete_annotations` | アノテーションを削除 |

### スキャン (3 tools)

| ツール名 | 説明 |
|---|---|
| `trigger_scan` | スキャン開始 |
| `get_scan_status` | スキャン進捗確認 |
| `get_scan_errors` | スキャンエラー一覧 |

### その他

プロンプトライブラリ、バックアップ、MCP クライアント管理のツールも含まれます。

## FAQ

### Q: アプリ内にチャット機能はないの？

A: ありません。YU AI Manager は画像メタデータ管理に特化しており、
対話型 AI の UI は MCP 対応クライアントに委ねる設計です。
Claude Desktop 等を裏で起動しておけば、自然言語で全操作が可能です。

### Q: どの LLM を使えばいい？

A: MCP クライアントが対応していればどの LLM でも構いません。
ツールの引数構造を正確に扱える観点では、Claude や GPT-4 クラスの
大規模モデルが安定して動作します。

### Q: ローカル LLM でも使える？

A: Open WebUI + Ollama の組み合わせなど、MCP に対応していれば
ローカル LLM でも利用できます。ただし、ツール呼び出しの精度は
モデルの能力に依存します。

### Q: YU AI Manager 側に MCP クライアント機能もあるけど？

A: `MCP Client` 拡張（Tools ページ）は、YU AI Manager から**他の MCP サーバー**に
接続するための機能です。本ガイドで説明しているのは逆方向
（外部 LLM → YU AI Manager）の接続です。
