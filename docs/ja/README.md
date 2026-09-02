# Documentation Hub

このファイルを「ドキュメント入口（正規ハブ）」として使ってください。

**最終更新**: 2026-05-13

## Important

- Project README: [`../../README.ja.md`](../../README.ja.md)
- Changelog: [`../../CHANGELOG.ja.md`](../../CHANGELOG.ja.md)
- Master TODO (single source of truth): [`../../TODO.md`](../../TODO.md)

## Development Guidelines

開発ガイドラインは `development/development_docs/` に個別ファイルとして配置されています。

- **[TODO Rules](TODO_RULES.md)** — TODO記述ルール（P0/P1/P2/P3 + カテゴリ必須）

### 主要ドキュメント (`development/development_docs/`)

| ドキュメント | 内容 |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | 300行で検討開始、500行で分割必須 |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | feature-unit directory、100-250行が理想 |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | 三層防御モデル (静的/パース/ランタイム検証) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` 統一、`{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | 全モジュール入口一覧 |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | 6つの事故ポイント防止策 |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Tier A/B/C ボタン設計 |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Explorer/Library hybrid pattern |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | ドキュメント配置ルール |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI ファズ/バーンインテスト |

### その他の開発ドキュメント

| ドキュメント | 内容 |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | AI 駆動開発の設計原則 |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | バッチ操作規約 |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Extension フックライフサイクル |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | 再利用 UI ウィジェット一覧 |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI プロンプト構文仕様 |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | アーカイブファイル名エンコーディング |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API 画像形式互換表 |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA ラウンド結果・残課題 |

### 開発ログ・仕様書

| ドキュメント | 内容 |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP 開発ログ |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX マルチバックエンド開発ログ |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo デバイス制御 |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | チャットログ拡張仕様 |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri デスクトップ統合 |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Freeze & Pull-back 拡張仕様 |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | 動画メタデータ v2 計画 (Draft) |

## Import Paths

全 import は実モジュールパスを直接使用。エイリアス機構は撤去済み。

**主要パス例:**
- `core.services_core.db_api` — DB アクセス (旧 `core.db`)
- `core.configuration.api` — 設定管理 (旧 `core.config`)
- `core.extensions_core.runtime` — 拡張ランタイム (旧 `core.extensions`)
- 新規機能は `core/<feature>_core/` ディレクトリに直接追加

## Troubleshooting & Operations

- Debug playbook: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Common errors (レガシー): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / 2バイト文字エンコーディングの罠: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- エスケープ括弧パースエラー: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| ドキュメント | ステータス | 内容 |
|---|---|---|
| [MCP 連携ガイド](features/mcp-integration-guide.md) | 現行 | LLM から YU AI Manager を操作 |
| [NovelAI V4](features/novelai-v4.md) | 現行 | NovelAI V4 プロンプト形式・キャラクター別ネガティブ対応 |
| [Hailo セマンティック検索](features/hailo-semantic-search.md) | 実装済 → ONNX 移行 | Hailo-10H CLIP 実装指示書 |
| [Danbooru タグ自動生成](features/danbooru-tag-gen-spec.md) | 実装済 (v2.77.0) | WD-Tagger + VLM 二段構え |
| [テキスト・チャットログ管理](features/text-chatlog-management-spec.md) | 現行 | Chatlog インポート・FTS検索 |
| [QR プロトコル v1](features/qr-protocol-v1.md) | 現行 | LAN 共有用 QR コード |
| [正規表現検索ベンチマーク](features/regex-search-benchmark.md) | 現行 | Regex パフォーマンス |
| [ブラウザ互換性](features/browser-compatibility.md) | 現行 | 対応ブラウザ一覧 |

## API Reference

- [API 概要 (認証・CSRF・レート制限)](api/README.md)
- [検索 API](api/search.md)
- [ファイル API](api/files.md)
- [スキャン API](api/scan.md)
- [SSE イベント](api/events.md)
- [テーマ CSS 変数](api/theming.md)

## Custom UI / Plugin Development

- [Custom UI ガイド](custom-ui/README.md) — カスタム UI 開発 (quickstart, design, templates, advanced)
- [Plugin 開発ガイド](plugin-development/getting-started.md) — Extension 開発入門
- [マニフェストリファレンス](plugin-development/manifest-reference.md) — extension.json 仕様

## Installation

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historical Docs

以下は過去の実装メモ/ホットフィックス記録です（`archive/docs_history/` に配置）。

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — v2.5.4 時代のデバッグ指示書
- `DARK_MODE_TAGS_IMPROVEMENT.md` — ダークモードタグ改善提案（実装済み）
- `EXTENSION_DRAFT.md` — Extension システム初期ドラフト（plugin-development/ に後継）
