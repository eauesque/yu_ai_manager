# MCP 連携

YU AI Manager は MCP (Model Context Protocol) サーバーを内蔵しており、
Claude Desktop、Claude Code、Cline などの AI クライアントから直接操作できます。
137 以上のツールを提供し、画像管理から AI 分析まで全機能にアクセス可能です。

## 対応 MCP クライアント

| クライアント | 接続方式 | 備考 |
|-------------|---------|------|
| Claude Desktop | stdio / HTTP | 推奨クライアント |
| Claude Code | stdio | CLI 環境 |
| Cline (VS Code) | stdio | VS Code 拡張機能 |
| Open WebUI | HTTP/SSE | Web ベース |

## ローカル接続（stdio）

同じマシン上の Claude Desktop / Claude Code から接続する場合:

1. Settings > API Keys タブで API キーを作成
2. クライアントの設定ファイルに以下を追加

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## LAN 接続（HTTP/SSE）

LAN 内の別マシンから接続する場合:

1. YU AI Manager で LAN Access を ON に設定
2. API キーを作成
3. Settings > API Keys タブの「MCP Connection Snippet」から接続設定をコピー

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## 利用可能なツール（カテゴリ別）

### 画像検索・管理

| ツール | 説明 |
|--------|------|
| `search_images` | タグ・日付・評価等でフィルター検索 |
| `get_image_detail` | 画像の詳細メタデータ取得 |
| `get_library_stats` | ライブラリ統計（ファイル数、タグ分布等） |
| `find_similar` | 知覚ハッシュによる類似画像検出 |
| `rate_images` | 星評価の一括設定 |
| `set_tags` | タグの追加・削除 |
| `set_annotations` | アノテーション設定 |
| `get_annotations` | アノテーション取得 |

### コレクション

| ツール | 説明 |
|--------|------|
| `list_collections` | コレクション一覧 |
| `create_collection` | コレクション作成 |
| `add_to_collection` | 画像をコレクションに追加 |
| `remove_from_collection` | 画像をコレクションから削除 |
| `delete_collection` | コレクション削除 |

### スキャン

| ツール | 説明 |
|--------|------|
| `trigger_scan` | スキャン実行 |
| `get_scan_status` | スキャン進捗確認 |
| `list_scan_roots` | スキャンルート一覧 |
| `add_scan_root` | スキャンルート追加 |
| `scan_directory` | 特定ディレクトリのスキャン |

### AI 分析

| ツール | 説明 |
|--------|------|
| `analyze_image` | AI 画像分析（単一） |
| `analyze_batch` | AI 画像分析（バッチ） |
| `wd_tagger_tag_file` | WD-Tagger 推論（単一） |
| `wd_tagger_batch` | WD-Tagger 推論（バッチ） |
| `semantic_search` | CLIP セマンティック検索 |
| `s2t_transcribe_video` | 音声テキスト化 |

### Bridge 連携

| ツール | 説明 |
|--------|------|
| `sd_generate` | SD WebUI で画像生成 |
| `sd_list_models` | SD WebUI モデル一覧 |
| `comfyui_generate` | ComfyUI で画像生成 |
| `comfyui_generate_json` | ComfyUI ワークフロー JSON 実行 |

### プロンプトライブラリ

| ツール | 説明 |
|--------|------|
| `create_prompt` | プロンプト作成 |
| `search_prompts` | プロンプト検索 |
| `get_prompt` | プロンプト取得 |
| `update_prompt` | プロンプト更新 |

### 設定

| ツール | 説明 |
|--------|------|
| `settings_get_schema` | 設定スキーマ取得 |
| `settings_get` | 設定値取得 |
| `settings_set` | 設定値更新 |
| `secrets_status` | 暗号化キー状態確認 |

### エージェント安全機構

| ツール | 説明 |
|--------|------|
| `agent_kill` / `agent_resume` | Kill Switch 制御 |
| `agent_status` | 安全機構ステータス |
| `agent_journal` | 操作ジャーナル検索 |
| `agent_undo` | 操作取り消し |
| `agent_circuit_breaker_status` | Circuit Breaker 状態 |
| `agent_budget_status` | 予算トラッカー状態 |
| `agent_scope_set` | スコープ設定 |
| `agent_anomaly_status` | 異常検知ステータス |

### その他

| ツール | 説明 |
|--------|------|
| `find_duplicates` | 重複ファイル検出 |
| `search_chat_logs` | チャットログ検索 |
| `search_md_files` | Markdown ファイル検索 |
| `help_search` | ヘルプドキュメント検索 |
| `share_to_bluesky` | Bluesky 投稿 |
| `list_trophies` | トロフィー一覧 |
| `get_monthly_report` | 月間レポート |

## 環境変数

| 変数 | 説明 | デフォルト |
|------|------|----------|
| `YU_BASE_URL` | サーバーの URL | `http://localhost:5000` |
| `YU_API_KEY` | API キー | (必須) |
| `YU_DEBUG_MODE` | デバッグツール有効化 | `0` |

`YU_DEBUG_MODE=1` を設定すると、DB 直接クエリやヘルスチェック等のデバッグ専用ツールが追加されます。

## トラブルシューティング

### 接続できない

1. YU AI Manager が起動しているか確認
2. API キーが正しいか確認（`sk_` プレフィックス付き）
3. `YU_BASE_URL` が正しいか確認
4. LAN 接続の場合、LAN Access が ON になっているか確認

### ツールが見つからない

- Extension が無効になっているとそのツールも利用不可になります
- `list_extensions` で有効状態を確認してください

### タイムアウトする

- 大規模ライブラリでの検索やバッチ操作は時間がかかる場合があります
- `limit` パラメータで結果数を制限してください
