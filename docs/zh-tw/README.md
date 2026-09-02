# 文檔中心

請將此檔案視為「文檔入口（正規中心）」。

**最後更新**: 2026-05-13

## 重要

- 專案 README: [`../../README.zh-tw.md`](../../README.zh-tw.md)
- 變更日誌: [`../../CHANGELOG.zh-tw.md`](../../CHANGELOG.zh-tw.md)
- 主要 TODO（唯一資訊來源）: [`../../TODO.md`](../../TODO.md)

## 開發指南

開發指南作為個別檔案放置在 `development/development_docs/` 中。

- **[TODO 規則](TODO_RULES.md)** — TODO 描述規則（P0/P1/P2/P3 + 類別必須）

### 主要文檔 (`development/development_docs/`)

| 文檔 | 內容 |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | 300 行開始考慮分割、500 行必須分割 |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | feature-unit 目錄、100-250 行為理想 |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | 三層防御模型（靜態/解析/運行時驗證） |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` 統一、`{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | 全模組入口清單 |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | 6 個事故要點防止策略 |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Tier A/B/C 按鈕設計 |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Explorer/Library 混合模式 |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | 文檔放置規則 |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI 模糊/老化測試 |

### 其他開發文檔

| 文檔 | 內容 |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | AI 驅動開發的設計原則 |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | 批次操作規約 |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | 擴充功能鉤子生命週期 |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | 可重用 UI 小部件清單 |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI 提示語法規範 |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | 檔案名編碼備用 |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API 影像格式相容性表 |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA 輪次結果·未解決問題 |

### 開發日誌·規範書

| 文檔 | 內容 |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP 開發日誌 |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX 多後端開發日誌 |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo 設備控制 |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | 聊天記錄擴展規範 |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri 桌面集成 |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | 凍結和回拉擴充功能規範 |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | 視訊中繼資料 v2 計劃（草稿） |

## 匯入路徑

所有匯入使用實模組路徑直接使用。別名機制已移除。

**主要路徑範例:**
- `core.services_core.db_api` — 資料庫存取（舊 `core.db`）
- `core.configuration.api` — 設定管理（舊 `core.config`）
- `core.extensions_core.runtime` — 擴充功能運行時（舊 `core.extensions`）
- 新功能直接添加到 `core/<feature>_core/` 目錄

## 疑難排解與操作

- 除錯指南: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- 常見錯誤（過時）: [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / 2 位元組字元編碼陷阱: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- 轉義括號解析錯誤: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## 功能

| 文檔 | 狀態 | 內容 |
|---|---|---|
| [MCP 集成指南](features/mcp-integration-guide.md) | 目前 | 從 LLM 控制 yu_ai_manager |
| [NovelAI V4](features/novelai-v4.md) | 目前 | NovelAI V4 提示格式·按角色負面對應 |
| [Hailo 語義搜尋](features/hailo-semantic-search.md) | 已實現 → ONNX 遷移 | Hailo-10H CLIP 實作指示書 |
| [Danbooru 標籤自動生成](features/danbooru-tag-gen-spec.md) | 已實現（v2.77.0） | WD-Tagger + VLM 雙層結構 |
| [文本·聊天記錄管理](features/text-chatlog-management-spec.md) | 目前 | 聊天記錄匯入·FTS 搜尋 |
| [QR 協議 v1](features/qr-protocol-v1.md) | 目前 | LAN 共享 QR 碼 |
| [正規表達式搜尋基準測試](features/regex-search-benchmark.md) | 目前 | 正規表達式效能 |
| [瀏覽器相容性](features/browser-compatibility.md) | 目前 | 支援的瀏覽器清單 |

## API 參考

- [API 概述（認證·CSRF·速率限制）](api/README.md)
- [搜尋 API](api/search.md)
- [檔案 API](api/files.md)
- [掃描 API](api/scan.md)
- [SSE 事件](api/events.md)
- [主題 CSS 變數](api/theming.md)

## 自訂 UI / 外掛開發

- [自訂 UI 指南](custom-ui/README.md) — 自訂 UI 開發（快速開始、設計、範本、進階）
- [外掛開發指南](plugin-development/getting-started.md) — 擴充功能開發入門
- [清單參考](plugin-development/manifest-reference.md) — extension.json 規範

## 安裝

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## 歷史文檔

以下是過去的實作備註/緊急修復記錄（放置在 `archive/docs_history/` 中）。

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — v2.5.4 時代的除錯指示書
- `DARK_MODE_TAGS_IMPROVEMENT.md` — 深色模式標籤改進提案（已實現）
- `EXTENSION_DRAFT.md` — 擴充功能系統初始草稿（後繼在 plugin-development/ 中）
