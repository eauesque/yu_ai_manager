# MCP ツールリファレンス

YU AI Manager の MCP (Model Context Protocol) サーバーが提供する全ツール一覧です。
Claude Desktop や他の MCP クライアントからこれらのツールを呼び出して、ライブラリの管理・分析・生成を自動化できます。

**総ツール数: 521**

## 目次

- [Search & Browse (10)](#search--browse-10)
- [Collections (7)](#collections-7)
- [Ratings & Tags (5)](#ratings--tags-5)
- [Favorites (8)](#favorites-8)
- [Annotations (4)](#annotations-4)
- [Scanning (14)](#scanning-14)
- [Scan Roots (9)](#scan-roots-9)
- [Hash & Duplicates (7)](#hash--duplicates-7)
- [Wait / Progress (2)](#wait--progress-2)
- [AI Analysis (25)](#ai-analysis-25)
- [WD-Tagger (15)](#wd-tagger-14)
- [Semantic Search / CLIP (12)](#semantic-search--clip-12)
- [YOLO Object Detection (17)](#yolo-object-detection-17)
- [OCR (19)](#ocr-19)
- [SD WebUI Bridge (14)](#sd-webui-bridge-14)
- [ComfyUI Bridge (13)](#comfyui-bridge-13)
- [NovelAI Bridge (8)](#novelai-bridge-8)
- [Hailo GenAI (10)](#hailo-genai-10)
- [Hailo Chat (7)](#hailo-chat-7)
- [Hailo Remote Tagger (7)](#hailo-remote-tagger-7)
- [Tagger Server Registry (13)](#tagger-server-registry-13)
- [Prompt Library (21)](#prompt-library-21)
- [Prompt Simulator (6)](#prompt-simulator-6)
- [Prompt Syntax (1)](#prompt-syntax-1)
- [SD/NAI Conversion (3)](#sdnai-conversion-3)
- [Chat Logs (16)](#chat-logs-16)
- [Markdown Viewer (8)](#markdown-viewer-8)
- [Freeze & Pull-back (6)](#freeze--pull-back-6)
- [Speech-to-Text (8)](#speech-to-text-8)
- [Statistics (6)](#statistics-6)
- [Profiles (11)](#profiles-11)
- [File Operations (4)](#file-operations-4)
- [SVG Rasterization (2)](#svg-rasterization-2)
- [Download (1)](#download-1)
- [Video Analysis (3)](#video-analysis-3)
- [Backup (5)](#backup-5)
- [Archive Cleanup (7)](#archive-cleanup-7)
- [Auto Scan Watcher (3)](#auto-scan-watcher-3)
- [Scheduler (6)](#scheduler-6)
- [Webhooks (9)](#webhooks-9)
- [Extensions (25)](#extensions-25)
- [UI Management (4)](#ui-management-4)
- [Settings (18)](#settings-18)
- [SNS Sharing (15)](#sns-sharing-15)
- [LAN Share (2)](#lan-share-2)
- [MCP Client (8)](#mcp-client-8)
- [Cross Search (9)](#cross-search-9)
- [Tag Dictionary (6)](#tag-dictionary-6)
- [Trophies (1)](#trophies-1)
- [Source Code Browsing (3)](#source-code-browsing-3)
- [Help (3)](#help-3)
- [System Info (3)](#system-info-3)
- [System Update (5)](#system-update-5)
- [Suggestions (4)](#suggestions-4)
- [Logs & Debug (9)](#logs--debug-9)
- [Agent Safety Gateway (25)](#agent-safety-gateway-25)
- [GitHub Integration (12)](#github-integration-12)
- [Debug Tools (9)](#debug-tools-9)
- [LoRA Dataset Manager (15)](#lora-dataset-manager-14)
- [LLM Endpoints (5)](#llm-endpoints-5)
- [LLM Chat (1)](#llm-chat-1)
- [Server Mode (1)](#server-mode-1)

---

## セットアップ

### 環境変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `YU_BASE_URL` | YU AI Manager サーバーの URL | `http://localhost:5000` |
| `YU_API_KEY` | API Key (Bearer 認証) | (なし) |
| `YU_DEBUG_MODE` | `1` でデバッグツールを有効化 | `0` |

### Claude Desktop 設定例 (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "/path/to/venv/bin/python",
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

### 進捗通知

`wait_for_scan` / `wait_for_batch` ツールは MCP Notifications に対応しています:
- **progressToken 対応クライアント**: `notifications/progress` でリアルタイム進捗を受信
- **非対応クライアント**: ブロッキング待機し、完了時に最終結果を返却

---

## Search & Browse (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_images` | 各種フィルタで画像を検索 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | ディレクトリグループ付きで画像を検索 | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | 複数クエリの和集合検索 | `queries`: list |
| `get_image_detail` | 画像の全メタデータを取得 | `file_id`: int |
| `get_library_stats` | ライブラリ統計 | — |
| `get_file_info` | ファイルパスとメタデータ情報 | `file_id`: int |
| `get_groups_index` | ディレクトリグループのインデックス | — |
| `get_group_members` | グループ内メンバー一覧 | `group`: str |
| `get_container_members` | ZIP/RAR コンテナ内メンバー一覧 | `file_id`: int |
| `file_search` | データベース内のファイルをパス・名前で検索 | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_collections` | 全コレクション一覧 | — |
| `create_collection` | コレクション作成 | `name`: str |
| `rename_collection` | コレクション名変更 | `collection_id`: int, `name`: str |
| `delete_collection` | コレクション削除 | `collection_id`: int |
| `reorder_collections` | コレクション並び順変更 | `order`: list |
| `add_to_collection` | 画像をコレクションに追加 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | 画像をコレクションから削除 | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `rate_images` | 複数画像のレーティングを一括設定 | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | ファイルのレーティング取得 | `file_ids`: str |
| `get_ratings_stats` | レーティング統計 | — |
| `set_tags` | 複数画像のユーザータグを追加/削除 | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | DB 内タグの正規化 | — |

## Favorites (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `toggle_favorite` | お気に入り切替 | `file_id`: int |
| `check_favorite` | お気に入り状態の確認 | `file_id`: int |
| `check_favorite_collections` | お気に入りファイルのコレクション所属確認 | `file_id`: int |
| `list_favorites` | お気に入り一覧 | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | 複数ファイルをお気に入りに一括追加 | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | 複数ファイルをお気に入りから一括削除 | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | お気に入りをサーバー上のフォルダにエクスポート | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | お気に入りコレクション内の画像一覧 | `collection_id`: int = 0 |

## Annotations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `set_annotations` | アノテーションを保存 (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | 画像のアノテーション取得 | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | アノテーション横断検索 | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | アノテーション削除 | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `trigger_scan` | 全スキャンルートのスキャン開始 | — |
| `start_scan` | 指定パスまたは全ルートのスキャン開始 | `path`: str = '' |
| `get_scan_status` | スキャン進捗取得 | — |
| `cancel_scan` | スキャンキャンセル | — |
| `resume_scan` | 中断スキャンの再開 | — |
| `dismiss_interrupted_scan` | 中断状態の破棄 | — |
| `get_scan_interrupted` | 中断スキャン情報取得 | — |
| `get_scan_errors` | スキャンエラー一覧 | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | エラーを解決済みにマーク | `error_id`: int |
| `clear_scan_errors` | 解決済みエラーをクリア | — |
| `get_scanned_roots` | スキャン済みルート一覧 | — |
| `scan_queue_list` | スキャンキューの待機アイテム一覧 | -- |
| `scan_queue_remove` | スキャンキューからアイテムを削除 | `queue_id`: str |
| `scan_queue_clear` | スキャンキューを全クリア | -- |

## Scan Roots (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_scan_roots` | スキャンルート一覧 | — |
| `add_scan_root` | スキャンルート追加 | `path`: str |
| `edit_scan_root` | スキャンルートパス編集 | `index`: int, `path`: str |
| `remove_scan_root` | スキャンルート削除 | `index`: int |
| `toggle_scan_root` | スキャンルート有効/無効切替 | `index`: int |
| `reorder_scan_roots` | スキャンルート並び順変更 | `order`: list |
| `scan_directory` | 特定ディレクトリのスキャン | `path`: str |
| `get_checkpoints` | 利用可能モデルチェックポイント | — |
| `purge_scanned_roots` | スキャン済みルートレコードのパージ | — |

## Hash & Duplicates (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `find_duplicates` | 重複ファイル検出 | `method`: str = 'hash' |
| `find_similar` | 知覚ハッシュで類似画像検索 | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | ファイルハッシュ計算ジョブ開始 | `hash_type`: str = 'both' |
| `delete_duplicates` | 重複ファイル削除 | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | 未計算ハッシュの一括計算開始 | — |
| `cancel_hash_backfill` | ハッシュ計算キャンセル | — |
| `get_hash_backfill_status` | ハッシュ計算進捗 | — |

## Wait / Progress (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wait_for_scan` | スキャン完了まで待機 (進捗通知対応) | `timeout`: int = 600 |
| `wait_for_batch` | バッチジョブ完了まで待機 (進捗通知対応) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_image` | 単一画像の AI 分析 | `file_id`: int |
| `analyze_batch` | 複数画像の一括 AI 分析 | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | 実行中のAI分析バッチジョブをキャンセル | -- |
| `get_analysis_result` | 分析結果取得 | `file_id`: int |
| `get_analysis_stats` | 分析統計 | — |
| `get_analysis_config` | 分析設定取得 | — |
| `save_analysis_config` | 分析設定保存 | `config`: dict |
| `get_available_engines` | 利用可能エンジン一覧 | — |
| `get_ollama_models` | Ollama モデル一覧 | — |
| `test_ollama_connection` | Ollama 接続テスト | — |
| `get_openai_compat_models` | OpenAI 互換 API モデル一覧 | — |
| `test_openai_compat_connection` | OpenAI 互換 API 接続テスト | — |
| `list_ai_servers` | 登録済み AI サーバー一覧 | — |
| `add_ai_server` | AI サーバー登録 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | AI サーバー設定更新 | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | AI サーバー削除 | `server_id`: str |
| `set_active_ai_server` | アクティブサーバー切替 | `server_id`: str |
| `test_ai_server` | AI サーバー接続テスト | `server_id`: str |
| `reorder_ai_servers` | サーバー優先順位変更 | `order`: list |
| `migrate_ai_servers` | 旧設定からの移行 | — |
| `analyze_prompt_trends` | プロンプトトレンド分析 | `limit`: int = 100 |
| `get_trend_history` | トレンド分析履歴 | `limit`: int = 20 |
| `delete_trend_history` | トレンド履歴削除 | `history_id`: int |
| `analyze_video` | マルチキーフレーム動画分析 (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | 音声/動画ファイルを Whisper で文字起こし | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | 音声分析の利用可能状況を確認 (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wd_tagger_tag_file` | 単一ファイルにタグ推論 | `file_id`: int |
| `wd_tagger_batch` | 複数ファイルに一括タグ推論 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | 実行中のWD-Taggerバッチジョブをキャンセル | -- |
| `wd_tagger_get_tags` | ファイルの WD-Tagger タグ取得 | `file_id`: int |
| `wd_tagger_delete_tags` | ファイルの WD-Tagger タグ削除 | `file_id`: int |
| `wd_tagger_delete_tags_batch` | 複数ファイルの WD-Tagger タグ一括削除 | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | XMP メタデータ取得 | `file_id`: int |
| `wd_tagger_stats` | タグ統計 | — |
| `wd_tagger_untagged` | 未タグファイル一覧 | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | 設定取得 | — |
| `wd_tagger_save_config` | 設定保存 | `config`: dict |
| `wd_tagger_model_status` | モデルダウンロード状態 | — |
| `wd_tagger_download_model` | モデルダウンロード | — |
| `wd_tagger_vlm_test` | VLM サーバー接続テスト | `url`: str |
| `wd_tagger_vlm_models` | VLM サーバーモデル一覧 | `url`: str |

## Semantic Search / CLIP (12)

| Tool | Description | Parameters |
|------|-------------|------------|
| `semantic_search` | 自然言語テキストで画像を検索 | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | Extension ステータス | — |
| `semantic_backend_info` | CLIP バックエンド情報 | — |
| `semantic_model_status` | モデル状態 | — |
| `semantic_model_download` | CLIP モデルダウンロード | — |
| `semantic_index_start` | インデックス構築開始 | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | インデックス進捗 | — |
| `semantic_index_stop` | インデックス構築停止 | — |
| `semantic_index_clear` | インデックスクリア | — |
| `semantic_caption_start` | バッチキャプション生成開始 | `batch_size`: int = 50 |
| `semantic_caption_status` | キャプション進捗 | — |
| `semantic_caption_stop` | キャプション停止 | — |

## YOLO Object Detection (17)

| Tool | Description | Parameters |
|------|-------------|------------|
| `yolo_status` | Extension ステータス | — |
| `yolo_detect_start` | 物体検出開始 | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | 検出ジョブ進捗 | — |
| `yolo_detect_stop` | 検出停止 | — |
| `yolo_get_results` | ファイルの検出結果取得 | `file_id`: int |
| `yolo_search` | 検出ラベルで画像検索 | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | 検出結果クリア | `file_ids`: list = None |
| `yolo_model_status` | モデル状態 | — |
| `yolo_model_download` | YOLO HEF モデルダウンロード | — |
| `yolo_list_labels` | 検出済みラベル一覧 | — |
| `yolo_stream_sources` | ストリームソース一覧・状態取得 | — |
| `yolo_stream_start` | ストリームソース開始 | `source_id`: str |
| `yolo_stream_stop` | ストリームソース停止 | `source_id`: str |
| `yolo_stream_add_source` | ストリームソース追加 | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | 検出ルール一覧取得 | — |
| `yolo_stream_add_rule` | 検出ルール追加 | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | ストリーム全体ステータス（パイプライン・ソース・ルール・録画） | — |

## OCR (19)

| Tool | Description | Parameters |
|------|-------------|------------|
| `ocr_extract` | 画像から OCR テキスト抽出を実行 | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | 複数ファイルに OCR を実行 | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | ファイルの OCR 結果を取得 | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | ファイルの OCR 結果を削除 | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | OCR 結果を指定フォーマットでエクスポート | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | OCR 結果を翻訳 | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | ファイルの翻訳結果を取得 | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | 動画キーフレームに OCR を実行 | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | OCR 結果のバウンディングボックス検出を実行 | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | OCR オーバーレイ画像を生成 | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | OCR 結果を一括エクスポート | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | PDF ドキュメントに OCR を実行 | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | 利用可能な OCR エンジンと能力スコア一覧 | -- |
| `ocr_profiles` | 全モデル能力プロファイル一覧 | -- |
| `ocr_profiles_fetch` | コミュニティモデルプロファイルを URL から取得・マージ | `url`: str |
| `ocr_profile_update` | モデルの能力スコアを手動更新 | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | OCR ベンチマークで精度測定 | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | 利用可能なベンチマークテストケース一覧 | `benchmark_dir`: str = "" |
| `ocr_npu_status` | NPU の利用可能状況と最適化提案を確認 | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `sd_test_connection` | 接続テスト | — |
| `sd_generate` | txt2img 画像生成 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | 生成進捗 | — |
| `sd_cancel` | 生成キャンセル | — |
| `sd_list_models` | チェックポイントモデル一覧 | — |
| `sd_list_samplers` | サンプラー一覧 | — |
| `sd_list_loras` | LoRA 一覧 | `q`: str = '' |
| `sd_list_embeddings` | Embedding 一覧 | `q`: str = '' |
| `sd_list_scripts` | スクリプト一覧 | — |
| `sd_get_script_info` | スクリプト詳細 | — |
| `sd_list_extensions` | Extension 一覧 | — |
| `sd_list_upscalers` | アップスケーラー一覧 | — |
| `sd_get_config` | 設定取得 | — |
| `sd_save_config` | 設定保存 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `comfyui_test_connection` | 接続テスト | — |
| `comfyui_generate` | txt2img 画像生成 | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | JSON ワークフローで生成 | `workflow`: str |
| `comfyui_get_progress` | 生成進捗 | — |
| `comfyui_cancel` | 生成キャンセル | — |
| `comfyui_list_models` | チェックポイントモデル一覧 | — |
| `comfyui_list_samplers` | サンプラー一覧 | — |
| `comfyui_list_schedulers` | スケジューラ一覧 | — |
| `comfyui_list_loras` | LoRA 一覧 | `q`: str = '' |
| `comfyui_list_embeddings` | Embedding 一覧 | `q`: str = '' |
| `comfyui_list_custom_nodes` | カスタムノード一覧 | `q`: str = '' |
| `comfyui_get_config` | 設定取得 | — |
| `comfyui_save_config` | 設定保存 | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `nai_test_connection` | 接続テスト | — |
| `nai_get_anlas` | Anlas 残高取得 | — |
| `nai_generate` | 画像生成 | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | モデル一覧 | — |
| `nai_list_samplers` | サンプラー一覧 | — |
| `nai_list_noise_schedules` | ノイズスケジュール一覧 | — |
| `nai_get_config` | 設定取得 | — |
| `nai_save_config` | 設定保存 | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_genai_status` | Extension ステータス | — |
| `hailo_genai_model_status` | モデルロード状態 | — |
| `hailo_genai_model_download` | モデルダウンロード | `model_name`: str = '' |
| `hailo_genai_model_unload` | モデルアンロード | — |
| `hailo_llm_generate` | LLM テキスト生成 | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | LLM コンテキストクリア | — |
| `hailo_vlm_generate` | VLM 画像→テキスト生成 | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Hailo LLM パフォーマンスベンチマーク実行 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Hailo vs Ollama LLM パフォーマンス比較 | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Hailo GenAI の OpenAI 互換 API エンドポイント情報取得 | -- |

## Hailo Chat (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_chat_new` | 新しい Hailo Chat 会話を作成 | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Hailo Chat 会話一覧 | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | 全メッセージ付きで会話を取得 | `conversation_id`: int |
| `hailo_chat_active` | 現在アクティブな会話 ID を取得 | -- |
| `hailo_chat_search` | DuckDuckGo 経由の Web 検索 (コンテキスト注入用) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | 会話の名前変更 | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | 会話を削除 | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Hailo リモートタガーで単一ファイルをタグ付け | `file_id`: int |
| `hailo_tagger_batch` | 複数ファイルを一括タグ付け（最大 500） | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Hailo リモートタガー接続状態確認 | — |
| `hailo_tagger_get_config` | Hailo リモートタガー設定取得 | — |
| `hailo_tagger_save_config` | Hailo リモートタガー設定保存 | `config`: dict |
| `hailo_tagger_get_tags` | ファイルの Hailo タグ取得 | `file_id`: int |
| `hailo_tagger_delete_tags` | ファイルの Hailo タグ削除 | `file_id`: int |

## Tagger Server Registry (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `tagger_servers_list` | 登録タガーサーバー一覧と分散モード取得 | -- |
| `tagger_servers_add` | タガーサーバー追加 | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | タガーサーバー設定更新 | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | タガーサーバー削除 | `server_id`: str |
| `tagger_servers_test` | タガーサーバー接続テスト | `server_id`: str |
| `tagger_servers_health` | 全有効サーバーのヘルスチェック | -- |
| `tagger_servers_set_mode` | 分散モード設定 (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | 分散バッチタグ付け（共有キューワークスティーリング） | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | 実行中のタガークラスターバッチジョブをキャンセル | -- |
| `tagger_servers_tags` | ファイルのタガータグ取得 | `file_id`: int |
| `tagger_servers_delete_tags` | ファイルのタガータグ削除 | `file_id`: int |
| `tagger_servers_stats` | タガー統計（未タグファイル数） | -- |
| `tagger_servers_migrate_legacy` | レガシー hailo_tagger 設定をレジストリ形式に移行 | -- |

## Prompt Library (21)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_prompts` | プロンプト検索 | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | プロンプト詳細取得 | `prompt_id`: int |
| `create_prompt` | プロンプト作成 | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | 画像メタデータからプロンプト作成 | `file_id`: int |
| `update_prompt` | プロンプト更新 (部分更新) | `prompt_id`: int, ... |
| `delete_prompt` | プロンプト削除 | `prompt_id`: int |
| `list_prompt_folders` | フォルダ一覧 | — |
| `create_prompt_folder` | フォルダ作成 | `name`: str |
| `update_prompt_folder` | フォルダ名変更 | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | フォルダ削除 | `folder_id`: int |
| `move_prompt_to_folder` | プロンプトをフォルダに移動 | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | フォルダから外す (ルートへ) | `prompt_id`: int |
| `list_prompt_tags` | タグ一覧 | — |
| `create_prompt_tag` | タグ作成 | `name`: str |
| `delete_prompt_tag` | タグ削除 | `tag_id`: int |
| `set_prompt_tags` | プロンプトのタグ設定 | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | 一括削除 | `prompt_ids`: list |
| `bulk_move_prompts` | 一括移動 | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | 一括タグ付け | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | 全プロンプト JSON エクスポート | — |
| `import_prompts` | プロンプト JSON インポート | `data`: dict |

## Prompt Simulator (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `prompt_dp_analyze` | Dynamic Prompts 構文解析 | `text`: str |
| `prompt_emphasis` | エンファシス構文変換 | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | A1111 ↔ NAI 形式変換 | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | ワイルドカード一覧 | — |
| `prompt_set_wildcard_dirs` | ワイルドカードディレクトリ設定 | `dirs`: list |
| `prompt_danbooru_autocomplete` | Danbooru タグ補完 | `q`: str |

## Prompt Syntax (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_prompt_syntax` | プロンプト構文解析 (トークン情報) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_sd_to_nai` | SD → NAI プロンプト変換 | `text`: str |
| `convert_nai_to_sd` | NAI → SD プロンプト変換 | `text`: str |
| `convert_prompt_batch` | バッチプロンプト変換 | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_chat_logs` | FTS5 全文検索 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | 会話単位でグループ化検索 | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | 会話詳細 (全メッセージ) | `conversation_id`: int |
| `get_chat_full` | get_conversation のエイリアス | `conversation_id`: int |
| `get_chat_summary` | AI 生成要約 | `conversation_id`: int |
| `get_chat_decisions` | AI 抽出決定事項 | `conversation_id`: int |
| `get_related_conversations` | 関連会話 | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | エンティティで会話検索 | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | トピック検索 | `topic`: str, `limit`: int = 50 |
| `search_decisions` | 決定事項横断検索 | `query`: str, `limit`: int = 50 |
| `import_chat_log` | ローカルファイルからインポート | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | インポート進捗 | — |
| `get_chatlog_stats` | チャットログ統計 | — |
| `delete_conversation` | 会話削除 | `conversation_id`: int |
| `reprocess_chat_logs` | AI 再処理 | `target`: str = 'unprocessed' |
| `text_search` | MD/チャット/プロンプト横断検索 | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_md_files` | Markdown ファイル検索 | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | ファイル内容取得 | `file_id`: int |
| `get_md_scan_roots` | スキャンルート一覧 | — |
| `set_md_scan_roots` | スキャンルート設定 | `roots`: list |
| `remove_md_scan_root` | スキャンルート削除 | `index`: int |
| `trigger_md_scan` | スキャン開始 | — |
| `get_md_scan_status` | スキャン進捗 | — |
| `get_md_stats` | 統計 | — |

## Freeze & Pull-back (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `generate_freeze_pullback` | Ken Burns 動画生成 | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | レンダージョブ状態 | — |
| `fpb_check` | 前提条件チェック (ffmpeg 等) | — |
| `fpb_cancel` | 生成キャンセル | — |
| `fpb_list_outputs` | 出力ファイル一覧 | — |
| `fpb_delete_output` | 出力ファイル削除 | `filename`: str |

## Speech-to-Text (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `s2t_status` | バックエンド状態 | — |
| `s2t_transcribe_video` | 動画/音声の文字起こし | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | バッチ文字起こし | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | 保存済み文字起こし取得 | `file_id`: int |
| `s2t_stream_start` | ストリーム文字起こし開始 | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | ストリーム文字起こし停止 | — |
| `s2t_stream_status` | ストリーム状態取得 | — |
| `s2t_stream_transcript` | ストリーム文字起こし結果取得 | — |

## Statistics (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_stats_timeline` | タイムライン統計 | `period`: str = 'daily' |
| `get_stats_hourly` | 時間帯別統計 | — |
| `get_stats_models` | モデル使用統計 | — |
| `get_stats_resolutions` | 解像度分布統計 | — |
| `get_stats_story` | ライブラリストーリーナラティブ | — |
| `get_monthly_report` | 月次レポート | `month`: str = '' |

## Profiles (11)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_profiles` | プロファイル一覧 | — |
| `get_profile` | プロファイル取得 | `name`: str |
| `create_profile` | プロファイル作成 | `name`: str, `description`: str = '' |
| `update_profile` | プロファイル更新 | `name`: str, `settings`: dict |
| `delete_profile` | プロファイル削除 | `name`: str |
| `duplicate_profile` | プロファイル複製 | `name`: str, `new_name`: str |
| `rename_profile` | プロファイル名変更 | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | お気に入り切替 | `name`: str |
| `export_profile` | プロファイルエクスポート | `name`: str |
| `import_profile` | エクスポートデータからプロファイルをインポート | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | プロファイルインポートのプレビュー | `qr_data`: str |

## File Operations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_image` | 画像形式変換 | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | ZIP からファイル抽出 | `file_id`: int, `members`: list |
| `inspect_metadata` | 生メタデータ検査 | `file_id`: int |
| `get_share_link` | シェアリンク生成 | `file_id`: int |

## SVG Rasterization (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `svg_info` | SVG ラスタライズの利用可否・バックエンド情報を取得 | — |
| `svg_rasterize` | SVG を PNG/WebP にラスタライズ。返却される base64 は img2img の入力に直接利用可能 | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `batch_download_zip` | 複数画像を ZIP でダウンロード | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_video_analysis_config` | 動画分析設定取得 | — |
| `save_video_analysis_config` | 動画分析設定保存 | `config`: dict |
| `get_video_analysis_status` | 動画分析状態 | — |

## Backup (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_backups` | バックアップ一覧 | — |
| `create_backup` | バックアップ作成 | — |
| `restore_backup` | バックアップ復元 | `filename`: str |
| `delete_backup` | バックアップ削除 | `filename`: str |
| `get_backup_status` | バックアップ状態 | — |

## Archive Cleanup (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `archive_cleanup_scan` | アーカイブペアスキャン | `path`: str = '' |
| `archive_cleanup_execute` | クリーンアップ実行 | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | LLM でアクション検証 (単一) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | LLM でアクション検証 (バッチ) | `items`: list |
| `archive_cleanup_get_llm_config` | LLM 設定取得 | — |
| `archive_cleanup_save_llm_config` | LLM 設定保存 | `config`: dict |
| `archive_cleanup_list_models` | 利用可能 LLM モデル一覧 | — |

## Auto Scan Watcher (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `auto_scan_info` | 監視ステータス | — |
| `auto_scan_start` | ファイル監視開始 | — |
| `auto_scan_stop` | ファイル監視停止 | — |

## Scheduler (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_scheduler_status` | タスクスケジューラのステータスと登録ジョブ取得 | -- |
| `list_scheduled_jobs` | 全スケジュールジョブのトリガーと次回実行時刻一覧 | -- |
| `trigger_scheduled_job` | スケジュールジョブの即時実行をトリガー | `job_id`: str |
| `pause_scheduled_job` | スケジュールジョブを一時停止 | `job_id`: str |
| `resume_scheduled_job` | 一時停止中のスケジュールジョブを再開 | `job_id`: str |
| `get_scheduler_history` | スケジュールジョブの最近の実行履歴取得 | -- |

## Webhooks (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_webhooks` | Webhook 一覧 | — |
| `create_webhook` | Webhook 作成 | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Webhook 更新 | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Webhook 削除 | `webhook_id`: str |
| `test_webhook` | テストイベント送信 | `webhook_id`: str |
| `get_webhook_deliveries` | 配信履歴 | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | 外部トリガー用の inbound webhook を作成。token URL を返す。 | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | 登録済み inbound webhook の一覧を取得。 | — |
| `delete_inbound_webhook` | inbound webhook を削除。 | `webhook_id`: str |

## Extensions (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_extensions` | Extension 一覧 | — |
| `get_extension_detail` | Extension 詳細 | `name`: str |
| `toggle_extension` | 有効/無効切替 | `name`: str, `enabled`: bool |
| `install_extension` | Git リポジトリからインストール | `url`: str |
| `update_extension` | Extension 更新 | `name`: str |
| `update_all_extensions` | 全 Extension 一括更新 | — |
| `uninstall_extension` | Extension アンインストール | `name`: str |
| `search_marketplace` | マーケットプレイス検索 | `query`: str = '' |
| `refresh_marketplace` | マーケットプレイスカタログ更新 | — |
| `get_extension_config` | 設定取得 | `name`: str |
| `set_extension_config` | 設定更新 | `name`: str, `values`: dict |
| `get_extension_permissions` | 権限情報取得 | `name`: str |
| `approve_extension_permissions` | 権限承認/拒否 | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | コード静的解析 | `name`: str |
| `rescan_extension` | コード再スキャン | `name`: str |
| `get_extension_tokens` | Capability Token 状態 | `name`: str |
| `get_extension_integrity` | ファイル整合性・監視状態 | `name`: str |
| `get_extension_hooks` | 登録済みフック一覧 | — |
| `get_extension_isolation_status` | プロセス隔離状態 | — |
| `get_extension_os_isolation_status` | OS レベル隔離状態 | — |
| `create_extension` | カスタム Extension をスキャフォールド付きで新規作成 | `name`: str, `description`: str = "" |
| `validate_extension` | Extension のマニフェストとコードを検証 | `extension_name`: str |
| `list_extension_files` | カスタム Extension のファイル一覧 | `extension_name`: str |
| `read_extension_file` | カスタム Extension のファイルを読み取り | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | カスタム Extension にファイルを書き込み | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_uis` | UI 一覧 | — |
| `switch_ui` | アクティブ UI 切替 | `name`: str |
| `install_ui` | UI インストール | `url`: str |
| `uninstall_ui` | UI アンインストール | `name`: str |

## Settings (18)

| Tool | Description | Parameters |
|------|-------------|------------|
| `settings_get_schema` | 設定スキーマ取得 | — |
| `settings_get_all` | 全設定取得 | — |
| `settings_get` | 個別設定取得 | `key`: str |
| `settings_set` | 設定更新 | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | レガシー config.json 取得 | — |
| `save_legacy_config` | レガシー config.json 保存 | `config`: dict |
| `secrets_status` | 暗号化キー状態 | — |
| `secrets_export` | 暗号化キーエクスポート | `password`: str |
| `secrets_import` | 暗号化キーインポート | `export_json`: str, `password`: str |
| `get_op_status` | 1Password CLI 状態 | — |
| `delete_op_mapping` | 1Password マッピング削除 | `key`: str |
| `migrate_secrets_to_keychain` | OS キーチェーンへ移行 | — |
| `get_bw_status` | Bitwarden CLI 統合ステータス取得 | -- |
| `list_bw_folders` | Bitwarden フォルダ一覧 | -- |
| `delete_bw_mapping` | Bitwarden フィールドマッピングを削除 | `key`: str |
| `list_op_vaults` | 1Password Vault 一覧 | -- |
| `push_secrets_to_1password` | 全シークレットを 1Password にプッシュし op_secrets マッピングを自動リンク | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | 全シークレットを Bitwarden にプッシュしマッピングを自動リンク | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `share_to_bluesky` | Bluesky に投稿 | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Bluesky 接続テスト | — |
| `get_x_share_url` | X (Twitter) シェア URL 取得 | `file_id`: int |
| `get_sns_preview` | SNS シェアプレビュー | `file_id`: int |
| `get_sns_config` | SNS 設定取得 | — |
| `save_sns_config` | SNS 設定保存 | `config`: dict |
| `bsky_get_pending_notifications` | 未読 Bluesky 通知をキューから取得 | -- |
| `bsky_get_notification_queue` | 通知キューアイテムをフィルター付きで取得 | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Bluesky 通知の即時ポーリングを実行 | -- |
| `bsky_triage_notification` | 通知のトリアージ結果を設定 | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | メンション/リプライ/引用への自動応答を送信 | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Bluesky モニター設定を取得 | -- |
| `bsky_save_monitor_config` | Bluesky モニター設定を保存 | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Bluesky トリアージプロンプトとテンプレートを取得 | -- |
| `bsky_save_triage_prompts` | Bluesky トリアージプロンプトを保存 | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_lan_share` | LAN 共有トークン作成 | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | 共有トークン失効 | `token`: str |

## MCP Client (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_mcp_connections` | MCP 接続一覧 | — |
| `create_mcp_connection` | MCP 接続作成 | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | MCP 接続更新 | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | MCP 接続削除 | `connection_id`: str |
| `connect_mcp_server` | MCP サーバーに接続 | `connection_id`: str |
| `disconnect_mcp_server` | MCP サーバーから切断 | `connection_id`: str |
| `get_mcp_connection_tools` | 接続先ツール一覧 | `connection_id`: str |
| `call_mcp_tool` | 接続先ツール呼び出し | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Cross Search スキャンルートディレクトリ取得 | -- |
| `cross_search_set_scan_roots` | Cross Search スキャンルートディレクトリ設定 | `roots`: list |
| `cross_search_delete_scan_root` | Cross Search スキャンルートをインデックスで削除 | `index`: int |
| `cross_search_scan` | Cross Search テキストファイルスキャン開始 | -- |
| `cross_search_scan_stop` | 実行中の Cross Search スキャンを停止 | -- |
| `cross_search_scan_status` | Cross Search スキャン進捗状況取得 | -- |
| `cross_search_get_txt` | Cross Search インデックス済みファイルのテキスト内容取得 | `file_id`: int |
| `cross_search_open_file` | システムファイルマネージャーでファイルを開く | `path`: str |
| `cross_search_stats` | Cross Search 統計情報取得 | -- |

## Tag Dictionary (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_tag_dictionary` | タグ辞書検索 | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | タグ辞書統計 | — |
| `split_tags` | 連結タグの分割 | `text`: str |
| `import_tag_dictionary` | タグ辞書インポート | `data`: dict |
| `clear_tag_dictionary` | タグ辞書クリア | — |
| `get_tag_dict_info` | 単一タグの詳細情報を取得 | `tag`: str |

## Trophies (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_trophies` | トロフィー一覧 | — |

## Source Code Browsing (3)

プロジェクトのソースコードを読み取り専用で安全に参照するツール群。
3 層セキュリティ (パス正規化 + 拡張子ホワイトリスト + 機密ファイルブロックリスト) で保護。
詳細: [`docs/api/source.md`](source.md)

| Tool | Description | Parameters |
|------|-------------|------------|
| `source_tree` | ディレクトリツリー表示 | `path`: str = '', `depth`: int = 3 |
| `source_read` | ファイル内容読み取り (行番号付き) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | ソースコード内テキスト検索 | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `help_toc` | ヘルプ目次 | — |
| `help_get_section` | セクション内容取得 | `section`: str |
| `help_search` | ヘルプ検索 | `query`: str, `limit`: int = 5 |

## System Info (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_server_info` | サーバー情報 | — |
| `get_inference_info` | 推論エンジン情報 | — |
| `get_market_quotes` | 市場情報 | — |

## System Update (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `check_for_update` | GitHub で新バージョンが利用可能か確認 | — |
| `get_update_status` | 現在のインストール方式とバージョンを取得 | — |
| `apply_system_update` | 利用可能な更新を適用 (git/portable のみ) | `confirm`: str |
| `check_unified_updates` | システム + 全 Extension の更新状態を一括チェック | `force`: bool (optional) |
| `apply_unified_updates` | システム + Extension を一括更新 (設定自動バックアップ付き) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_suggestions` | タグ/プロンプト補完 | `q`: str, `limit`: int = 10 |
| `suggest_tags` | タグ補完 | `q`: str, `limit`: int = 10 |
| `suggest_lora` | LoRA 名補完 | `q`: str = '' |
| `suggest_embedding` | Embedding 名補完 | `q`: str = '' |

## Logs & Debug (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_recent_logs` | 最近のログ取得 | `limit`: int = 100 |
| `get_debug_log` | デバッグログ出力 | `lines`: int = 200 |
| `clear_debug_log` | デバッグログクリア | — |
| `get_cache_info` | キャッシュ統計 | — |
| `clear_cache` | キャッシュクリア | — |
| `rebuild_groups` | ディレクトリグループ再構築 | — |
| `list_dirs` | ディレクトリ一覧 | `path`: str = '' |
| `debug_file_meta` | ファイルデバッグメタデータ | `file_id`: int |
| `debug_model_check` | モデル可用性チェック | — |

## Agent Safety Gateway (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `agent_status` | 安全機能の総合状態 | — |
| `agent_kill` | Kill Switch 起動 (全ツール即時ブロック) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Kill Switch 解除 | — |
| `agent_circuit_breaker_status` | Circuit Breaker 状態 | — |
| `agent_circuit_breaker_reset` | Circuit Breaker リセット | — |
| `agent_budget_status` | Budget Tracker 状態 | — |
| `agent_budget_reset` | Budget Tracker リセット | — |
| `agent_approval_status` | 承認待ちリクエスト一覧 | — |
| `agent_approval_respond` | 承認リクエストに応答 | `request_id`: str, `action`: str |
| `agent_approval_history` | 承認履歴 | `limit`: int = 50 |
| `agent_scope_status` | Scope Fence 状態 | — |
| `agent_scope_get` | セッション Scope 取得 | `session_id`: str |
| `agent_scope_set` | セッション Scope 設定 | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | セッション Scope 削除 | `session_id`: str |
| `agent_tool_level` | ツール安全レベル確認 | `tool_name`: str = '' |
| `agent_auto_approve_list` | 自動承認ルール一覧 | — |
| `agent_auto_approve_add` | 自動承認ルール追加 | `tool_name`: str |
| `agent_auto_approve_remove` | 自動承認ルール削除 | `index`: int |
| `agent_undo` | アクション取消 | `journal_id`: int |
| `agent_undoable` | 取消可能アクション一覧 | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | アクションジャーナル検索 | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | ジャーナル統計 | — |
| `agent_anomaly_status` | 異常検知状態 | — |
| `agent_anomaly_alerts` | 異常アラート履歴 | `limit`: int = 50 |
| `agent_anomaly_reset` | 異常検知リセット | — |

---

## GitHub Integration (12)

GitHub アカウントの issue 監視・トリアージ・レポート。

| Tool | Description | Parameters |
|------|-------------|------------|
| `github_list_accounts` | 登録済み GitHub アカウント一覧（トークンはマスク表示） | — |
| `github_fetch_issues` | アカウントのリポジトリから issue を取得 | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | issue を取得し分類（valid_bug / skip / needs_info）。優先度付きレポートを返す | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | issue の詳細を Claude Code 向けに構造化出力。コメント付き | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | GitHub API のレートリミット残量を確認 | `account_label`: str |
| `github_get_pending_issues` | ローカルキューから未処理の Issue を取得 | -- |
| `github_get_issue_queue` | Issue キューアイテムをステータスフィルター付きで取得 | `status`: str = "" |
| `github_poll_issues` | GitHub Issue の即時ポーリングを実行 | -- |
| `github_triage_queue_item` | キューの Issue にトリアージ結果を設定 | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | キューの Issue を却下 (オプションで自動 close) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Issue/PR/Discussion のトリアージプロンプトを取得 | `repo`: str = "" |
| `github_save_triage_prompts` | トリアージプロンプトを保存 | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

システム検証とデバッグ用ツール。`YU_DEBUG_MODE=1` で有効化。

| Tool | Description | Parameters |
|------|-------------|------------|
| `debug_health_check` | システムヘルスチェック: Flask, DB テーブル, スキーマバージョン | -- |
| `debug_validate_counts` | API 統計と DB カウントの交差検証 | -- |
| `debug_validate_search` | テストパターンで検索 API を検証 | `patterns`: str = "all" |
| `debug_validate_collection` | コレクションのキャッシュカウントと DB の検証 | -- |
| `debug_validate_annotations` | アノテーションデータの整合性検証 | -- |
| `debug_sample_files` | ランダムファイルをサンプリングしフィールド完全性を報告 | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | 書き込み-読み取り-更新-削除のラウンドトリップテスト | -- |
| `debug_readonly_query` | 読み取り専用 SQL クエリを実行 | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | 全デバッグ検証を一括実行 | -- |

---

## LoRA Dataset Manager (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_lora_projects` | プロジェクト一覧 | — |
| `get_lora_project` | プロジェクト詳細取得 | `project_id`: int |
| `create_lora_project` | プロジェクト作成 | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | プロジェクト更新 | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | プロジェクト削除 | `project_id`: int |
| `get_lora_project_tags` | タグ集計取得 | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | キャプションプレビュー | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | データセットエクスポート | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | エクスポート進捗確認 | `project_id`: int |
| `list_lora_checkpoints` | チェックポイント一覧 | — |
| `preview_lora_train_command` | 学習コマンドプレビュー (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | LoRA 学習開始 | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | 学習ステータス・ログ取得 | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | タグ除外プリセット一覧 | — |
| `create_lora_tag_preset` | タグ除外プリセット作成 | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm-endpoints-list` | 設定済み LLM エンドポイント一覧 | — |
| `llm-endpoints-set` | LLM エンドポイントの追加・更新 | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | LLM エンドポイントの削除 | `category`: str |
| `llm-endpoints-test` | LLM エンドポイントの接続テスト | `category`: str |
| `llm-chat` | 設定済み LLM にチャットを委任 | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `server-mode-get` | 現在のサーバーモードを取得 | — |
| `server-subsystems-status` | サブシステムのステータス一覧 | — |

## MCP 未対応の機能

以下は MCP の制約上、ツール化していません:

- **バイナリ返却**: サムネイル (`/api/thumbnail/`)、オリジナル画像 (`/api/original/`)、ZIP ダウンロード、動画ファイル
- **OS ダイアログ**: フォルダ選択ダイアログ (`/api/tools/select-folder`)、ファイルマネージャ起動 (`/api/open-folder/`)
- **SSE ストリーム**: ログストリーミング (`/api/logs/stream`)
- **認証ページ**: PIN 入力画面、LAN Share ゲストページ
