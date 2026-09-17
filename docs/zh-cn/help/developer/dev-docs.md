# 开发文档索引

内部设计文档、技术参考和开发日志的索引。
所有文件位于 `docs/development/development_docs/`。

也可以通过 MCP 的 `source_read` 工具直接读取。

---

## 设计与架构

| 文档 | 说明 |
|------|------|
| DESIGN_PHILOSOPHY | 设计哲学——项目全局原则与决策标准 |
| MODULE_ORGANIZATION_GUIDELINES | 模块组织准则 |
| CODE_SIZE_GUIDELINES | 代码大小准则（文件拆分标准） |
| ENTRYPOINT_MAP | 入口点映射 |
| DOCUMENT_LIFECYCLE | 文档生命周期策略 |
| UI_STATE_SPEC | UI 状态规范（Explorer/Library 混合） |
| NOTIFICATION_PROGRESS_DESIGN | 通知与进度显示设计 |

## API 与批处理

| 文档 | 说明 |
|------|------|
| API_RESPONSE_GUIDELINES | API 响应格式准则 |
| BATCH_API_STANDARD | 批处理 API 标准 |
| ERROR_HANDLING | 错误处理策略 |

## Extension 系统

| 文档 | 说明 |
|------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | 三权分立安全模型规范 |
| EXTENSION_SANDBOX_SPEC | 沙箱与权限规范 |
| EXTENSION_HOOKS_SPEC | Extension Hooks 规范 |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator 规范 |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core -> Extension 迁移规范 |

## AI 与 Agent 集成

| 文档 | 说明 |
|------|------|
| AGENT_INTEGRATION_DESIGN | AI Agent 集成设计指南 |
| AGENT_SAFETY_GATEWAY_SPEC | AI Agent Safety Gateway 规范 |
| AI_ANALYSIS_LANGUAGE | AI 分析响应语言规范 |
| MCP_DEBUG_TOOLS | MCP 调试工具规范 |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM 集成陷阱与解决方案 |
| OPENAI_COMPAT_API_DEVLOG | OpenAI 兼容 API 开发日志 |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing 与 OCR 设计规范 |
| VISION_API_IMAGE_FORMATS | Vision API 图片格式支持表 |
| ai-driven-development-principles | AI 驱动开发原则 |

## 数据库与性能

| 文档 | 说明 |
|------|------|
| SQLITE_READONLY_SEPARATION | SQLite 读写分离模式 |
| LARGE_SCALE_QUERY_OPTIMIZATION | 大规模 DB（280K 文件）查询优化 |

## 前端与 UI

| 文档 | 说明 |
|------|------|
| UI_AUDIT_GUIDE | 综合 UI 审计指南 |
| UI_BUTTON_PRIORITY_GUIDELINES | 按钮优先级准则（GC 手柄风格） |
| REUSABLE_UI_WIDGETS | 可复用 UI 组件集成指南 |
| VIRTUAL_SCROLL_PITFALLS | 虚拟滚动陷阱与已知 bug |
| IMAGE_DISPLAY_OPTIMIZATION | 图片显示优化技术参考 |
| MODAL_LOADING_OPTIMIZATION | 详情模态框加载优化 |
| MODAL_MEDIA_LIFECYCLE | 模态框媒体生命周期管理 |
| CONTAINER_VIEW_PERFORMANCE | 容器视图性能优化 |
| BROWSER_CONNECTION_SATURATION | 浏览器连接饱和导致结果缺失 |

## 视频处理

| 文档 | 说明 |
|------|------|
| VIDEO_STREAMING_ARCHITECTURE | 视频流架构 |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | 视频性能优化完整历史 |
| VIDEO_METADATA_V2_PLAN | Video Metadata v2 计划（草案） |

## 文件与归档处理

| 文档 | 说明 |
|------|------|
| NESTED_ZIP_HANDLING | 嵌套 ZIP 处理设计与陷阱 |
| ZIP_SCAN_PERFORMANCE | ZIP/7z 扫描性能优化 |
| ENCODING_FALLBACK | 归档文件名编码回退规范 |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD / NAI 提示词语法规范 |

## 跨平台与基础设施

| 文档 | 说明 |
|------|------|
| CROSS_PLATFORM_ISSUES | 跨平台差异指南 |
| DRAG_TO_SHARE_CROSS_PLATFORM | 拖放跨平台支持 |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio 事件循环阻塞修复 |
| MODULE_SAFETY | 模块安全加载设计 |
| DOCKER_SETUP | Docker 设置指南 |
| TAURI_DESKTOP_APP | Tauri 桌面应用开发指南 |

## 迁移

| 文档 | 说明 |
|------|------|
| QUART_MIGRATION_DEVLOG | Flask -> Quart（ASGI）迁移技术参考 |
| CHATLOG_ENHANCED_SPEC | 聊天记录增强规范 |

## 测试与质量

| 文档 | 说明 |
|------|------|
| FUZZ_BURN_IN_TEST | Fuzz / Burn-in 测试指南 |
| QA_HANDOFF | QA 交接文档 |
| yu-ai-manager-qa-agent-prompt | QA Agent 系统提示词 |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | 事故点与通用层速度指南 |
| BUG_VIDEO_AI_ANALYZED_FILTER | Bug 记录：Video + AI analyzed 过滤器 |

## 发布与翻译

| 文档 | 说明 |
|------|------|
| RELEASE_PROCEDURE | 发布流程 |
| TRANSLATION_STYLE_GUIDE | 日语 -> 英语翻译风格指南 |
