# 開發文件索引

內部設計文件、技術參考和開發記錄的索引。
所有檔案位於 `docs/development/development_docs/`。

也可以透過 MCP 的 `source_read` 工具直接讀取。

---

## 設計與架構

| 文件 | 說明 |
|------|------|
| DESIGN_PHILOSOPHY | 設計哲學——專案全域原則與決策標準 |
| MODULE_ORGANIZATION_GUIDELINES | 模組組織準則 |
| CODE_SIZE_GUIDELINES | 程式碼大小準則（檔案拆分標準） |
| ENTRYPOINT_MAP | 進入點對應 |
| DOCUMENT_LIFECYCLE | 文件生命週期政策 |
| UI_STATE_SPEC | UI 狀態規格（Explorer/Library 混合） |
| NOTIFICATION_PROGRESS_DESIGN | 通知與進度顯示設計 |

## API 與批次處理

| 文件 | 說明 |
|------|------|
| API_RESPONSE_GUIDELINES | API 回應格式準則 |
| BATCH_API_STANDARD | 批次 API 標準 |
| ERROR_HANDLING | 錯誤處理政策 |

## Extension 系統

| 文件 | 說明 |
|------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | 三權分立安全模型規格 |
| EXTENSION_SANDBOX_SPEC | 沙箱與權限規格 |
| EXTENSION_HOOKS_SPEC | Extension Hooks 規格 |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator 規格 |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core -> Extension 遷移規格 |

## AI 與 Agent 整合

| 文件 | 說明 |
|------|------|
| AGENT_INTEGRATION_DESIGN | AI Agent 整合設計指南 |
| AGENT_SAFETY_GATEWAY_SPEC | AI Agent Safety Gateway 規格 |
| AI_ANALYSIS_LANGUAGE | AI 分析回應語言規格 |
| MCP_DEBUG_TOOLS | MCP 除錯工具規格 |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM 整合陷阱與解決方案 |
| OPENAI_COMPAT_API_DEVLOG | OpenAI 相容 API 開發記錄 |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing 與 OCR 設計規格 |
| VISION_API_IMAGE_FORMATS | Vision API 圖片格式支援表 |
| ai-driven-development-principles | AI 驅動開發原則 |

## 資料庫與效能

| 文件 | 說明 |
|------|------|
| SQLITE_READONLY_SEPARATION | SQLite 讀寫分離模式 |
| LARGE_SCALE_QUERY_OPTIMIZATION | 大規模 DB（280K 檔案）查詢最佳化 |

## 前端與 UI

| 文件 | 說明 |
|------|------|
| UI_AUDIT_GUIDE | 綜合 UI 稽核指南 |
| UI_BUTTON_PRIORITY_GUIDELINES | 按鈕優先順序準則（GC 手把風格） |
| REUSABLE_UI_WIDGETS | 可重用 UI 元件整合指南 |
| VIRTUAL_SCROLL_PITFALLS | 虛擬捲動陷阱與已知 bug |
| IMAGE_DISPLAY_OPTIMIZATION | 圖片顯示最佳化技術參考 |
| MODAL_LOADING_OPTIMIZATION | 詳情模態框載入最佳化 |
| MODAL_MEDIA_LIFECYCLE | 模態框媒體生命週期管理 |
| CONTAINER_VIEW_PERFORMANCE | 容器檢視效能最佳化 |
| BROWSER_CONNECTION_SATURATION | 瀏覽器連線飽和導致結果缺失 |

## 影片處理

| 文件 | 說明 |
|------|------|
| VIDEO_STREAMING_ARCHITECTURE | 影片串流架構 |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | 影片效能最佳化完整歷史 |
| VIDEO_METADATA_V2_PLAN | Video Metadata v2 計畫（草案） |

## 檔案與歸檔處理

| 文件 | 說明 |
|------|------|
| NESTED_ZIP_HANDLING | 巢狀 ZIP 處理設計與陷阱 |
| ZIP_SCAN_PERFORMANCE | ZIP/7z 掃描效能最佳化 |
| ENCODING_FALLBACK | 歸檔檔案名稱編碼回退規格 |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD / NAI 提示詞語法規格 |

## 跨平台與基礎設施

| 文件 | 說明 |
|------|------|
| CROSS_PLATFORM_ISSUES | 跨平台差異指南 |
| DRAG_TO_SHARE_CROSS_PLATFORM | 拖放跨平台支援 |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio 事件迴圈阻塞修復 |
| MODULE_SAFETY | 模組安全載入設計 |
| DOCKER_SETUP | Docker 設定指南 |
| TAURI_DESKTOP_APP | Tauri 桌面應用程式開發指南 |

## 遷移

| 文件 | 說明 |
|------|------|
| QUART_MIGRATION_DEVLOG | Flask -> Quart（ASGI）遷移技術參考 |
| CHATLOG_ENHANCED_SPEC | 聊天記錄增強規格 |

## 測試與品質

| 文件 | 說明 |
|------|------|
| FUZZ_BURN_IN_TEST | Fuzz / Burn-in 測試指南 |
| QA_HANDOFF | QA 交接文件 |
| yu-ai-manager-qa-agent-prompt | QA Agent 系統提示詞 |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | 事故點與通用層速度指南 |
| BUG_VIDEO_AI_ANALYZED_FILTER | Bug 記錄：Video + AI analyzed 篩選器 |

## 發布與翻譯

| 文件 | 說明 |
|------|------|
| RELEASE_PROCEDURE | 發布流程 |
| TRANSLATION_STYLE_GUIDE | 日語 -> 英語翻譯風格指南 |
