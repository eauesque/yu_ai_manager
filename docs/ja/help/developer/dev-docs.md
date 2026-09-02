# 開発ドキュメント索引

内部設計書・技術資料・開発ログの一覧です。
全ファイルは `docs/development/development_docs/` に格納されています。

MCP の `source_read` ツールで直接読むこともできます。

---

## 設計・アーキテクチャ

| ドキュメント | 内容 |
|-------------|------|
| DESIGN_PHILOSOPHY | 設計哲学 — プロジェクト全体の方針と判断基準 |
| MODULE_ORGANIZATION_GUIDELINES | モジュール構成ガイドライン |
| CODE_SIZE_GUIDELINES | コードサイズガイドライン（ファイル分割基準） |
| ENTRYPOINT_MAP | エントリポイント一覧 |
| DOCUMENT_LIFECYCLE | ドキュメントライフサイクルポリシー |
| UI_STATE_SPEC | UI 状態仕様（Explorer/Library ハイブリッド） |
| NOTIFICATION_PROGRESS_DESIGN | 通知・進捗表示の設計方針 |

## API・バッチ処理

| ドキュメント | 内容 |
|-------------|------|
| API_RESPONSE_GUIDELINES | API レスポンス形式ガイドライン |
| BATCH_API_STANDARD | バッチ API 標準仕様 |
| ERROR_HANDLING | エラーハンドリングポリシー |

## Extension システム

| ドキュメント | 内容 |
|-------------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | 三権分立セキュリティモデル仕様書 |
| EXTENSION_SANDBOX_SPEC | Sandbox & Permission 仕様書 |
| EXTENSION_HOOKS_SPEC | Extension Hooks 仕様書 |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator 仕様 |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core → Extension 移行仕様書 |

## AI・エージェント連携

| ドキュメント | 内容 |
|-------------|------|
| AGENT_INTEGRATION_DESIGN | AI Agent 統合設計ガイド |
| AGENT_SAFETY_GATEWAY_SPEC | AI Agent Safety Gateway 仕様書 |
| AI_ANALYSIS_LANGUAGE | AI 分析 応答言語指定 |
| MCP_DEBUG_TOOLS | MCP デバッグツール仕様書 |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM 統合の落とし穴と対策 |
| OPENAI_COMPAT_API_DEVLOG | OpenAI 互換 API 開発ログ |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing & OCR 設計仕様書 |
| VISION_API_IMAGE_FORMATS | Vision API 画像形式対応表 |
| ai-driven-development-principles | AI 駆動開発の設計原則 |

## データベース・パフォーマンス

| ドキュメント | 内容 |
|-------------|------|
| SQLITE_READONLY_SEPARATION | SQLite 読み書き分離パターン |
| LARGE_SCALE_QUERY_OPTIMIZATION | 大規模 DB (280K ファイル) クエリ最適化 |

## フロントエンド・UI

| ドキュメント | 内容 |
|-------------|------|
| UI_AUDIT_GUIDE | UI 総合監査ガイド |
| UI_BUTTON_PRIORITY_GUIDELINES | ボタン優先度ガイドライン（GC コントローラ方式） |
| REUSABLE_UI_WIDGETS | 再利用 UI ウィジェット統合ガイド |
| VIRTUAL_SCROLL_PITFALLS | 仮想スクロール 注意事項・既知バグ集 |
| IMAGE_DISPLAY_OPTIMIZATION | 画像表示最適化 技術資料 |
| MODAL_LOADING_OPTIMIZATION | 詳細モーダル読み込み高速化 技術資料 |
| MODAL_MEDIA_LIFECYCLE | モーダルメディアライフサイクル管理 |
| CONTAINER_VIEW_PERFORMANCE | コンテナビュー パフォーマンス最適化 |
| BROWSER_CONNECTION_SATURATION | ブラウザ接続飽和による検索結果消失 |

## 動画処理

| ドキュメント | 内容 |
|-------------|------|
| VIDEO_STREAMING_ARCHITECTURE | 動画ストリーミングアーキテクチャ |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | 動画パフォーマンス最適化の全記録 |
| VIDEO_METADATA_V2_PLAN | Video Metadata v2 計画（ドラフト） |

## ファイル・アーカイブ処理

| ドキュメント | 内容 |
|-------------|------|
| NESTED_ZIP_HANDLING | ネスト ZIP 処理の設計と落とし穴 |
| ZIP_SCAN_PERFORMANCE | ZIP/7z スキャン パフォーマンス最適化 |
| ENCODING_FALLBACK | アーカイブファイル名エンコーディングフォールバック |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD / NAI プロンプト構文仕様書 |

## クロスプラットフォーム・インフラ

| ドキュメント | 内容 |
|-------------|------|
| CROSS_PLATFORM_ISSUES | クロスプラットフォーム差異ガイド |
| DRAG_TO_SHARE_CROSS_PLATFORM | ドラッグ&ドロップ クロスプラットフォーム対応 |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio イベントループブロッキング修正 |
| MODULE_SAFETY | モジュール安全読み込み設計 |
| DOCKER_SETUP | Docker 環境構築ガイド |
| TAURI_DESKTOP_APP | Tauri デスクトップアプリ開発ガイド |

## 移行・マイグレーション

| ドキュメント | 内容 |
|-------------|------|
| QUART_MIGRATION_DEVLOG | Flask → Quart (ASGI) 移行 技術資料 |
| CHATLOG_ENHANCED_SPEC | チャットログ拡張仕様書 |

## テスト・品質管理

| ドキュメント | 内容 |
|-------------|------|
| FUZZ_BURN_IN_TEST | Fuzz / Burn-in テストガイド |
| QA_HANDOFF | 品質調査 申し送り書 |
| yu-ai-manager-qa-agent-prompt | QA エージェント システムプロンプト |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | 事故多発ポイント・共通レイヤー速度ガイド |
| BUG_VIDEO_AI_ANALYZED_FILTER | バグ記録: 動画 + AI 解析済みフィルタ |

## リリース・翻訳

| ドキュメント | 内容 |
|-------------|------|
| RELEASE_PROCEDURE | リリース手順 |
| TRANSLATION_STYLE_GUIDE | 日英翻訳スタイルガイド |
