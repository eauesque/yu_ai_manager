# 文档中心

请将此文件用作"文档入口（正规中心）"。

**最后更新**: 2026-05-13

## 重要

- 项目 README: [`../../README.zh-cn.md`](../../README.zh-cn.md)
- 更新日志: [`../../CHANGELOG.zh-cn.md`](../../CHANGELOG.zh-cn.md)
- 总体 TODO（唯一真实来源）: [`../../TODO.md`](../../TODO.md)

## 开发指南

开发指南作为单独文件放在 `development/development_docs/` 中。

- **[TODO 规则](TODO_RULES.md)** — TODO 编写规则（P0/P1/P2/P3 + 必需类别）

### 主要文档 (`development/development_docs/`)

| 文档 | 内容 |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | 300 行开始考虑分割，500 行必须分割 |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | 特性单元目录，理想为 100-250 行 |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | 三层防御模型（静态/解析/运行时验证） |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` 统一，`{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | 所有模块入口列表 |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | 6 个事故点防止策略 |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | A/B/C 层级按钮设计 |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | 浏览器/库混合模式 |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | 文档位置规则 |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI 模糊/老化测试 |

### 其他开发文档

| 文档 | 内容 |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | AI 驱动开发设计原则 |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | 批量操作规约 |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | 扩展钩子生命周期 |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | 可重用 UI 小部件列表 |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI 提示词语法规范 |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | 存档文件名编码 |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API 图像格式兼容表 |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA 轮转结果·剩余课题 |

### 开发日志·规范书

| 文档 | 内容 |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP 开发日志 |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX 多后端开发日志 |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo 设备控制 |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | 聊天日志扩展规范 |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri 桌面集成 |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | 冻结 & 拉回扩展规范 |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | 视频元数据 v2 计划（草稿） |

## 导入路径

所有导入使用实模块路径直接引用。别名机制已移除。

**主要路径示例:**
- `core.services_core.db_api` — DB 访问（旧 `core.db`）
- `core.configuration.api` — 配置管理（旧 `core.config`）
- `core.extensions_core.runtime` — 扩展运行时（旧 `core.extensions`）
- 新功能直接添加到 `core/<feature>_core/` 目录

## 故障排除 & 操作

- 调试脚本: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- 常见错误（遗留）: [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / 双字节文字编码陷阱: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- 转义括号解析错误: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## 功能

| 文档 | 状态 | 内容 |
|---|---|---|
| [MCP 集成指南](features/mcp-integration-guide.md) | 现行 | 从 LLM 操作 YU AI Manager |
| [NovelAI V4](features/novelai-v4.md) | 现行 | NovelAI V4 提示词格式·按角色负面对应 |
| [Hailo 语义搜索](features/hailo-semantic-search.md) | 已实现 → ONNX 迁移 | Hailo-10H CLIP 实现指导 |
| [Danbooru 标签自动生成](features/danbooru-tag-gen-spec.md) | 已实现 (v2.77.0) | WD-Tagger + VLM 双层方案 |
| [文本·聊天日志管理](features/text-chatlog-management-spec.md) | 现行 | 聊天日志导入·FTS 搜索 |
| [QR 协议 v1](features/qr-protocol-v1.md) | 现行 | LAN 共享 QR 码 |
| [正则表达式搜索基准](features/regex-search-benchmark.md) | 现行 | 正则性能 |
| [浏览器兼容性](features/browser-compatibility.md) | 现行 | 支持的浏览器列表 |

## API 参考

- [API 概览（认证·CSRF·速率限制）](api/README.md)
- [搜索 API](api/search.md)
- [文件 API](api/files.md)
- [扫描 API](api/scan.md)
- [SSE 事件](api/events.md)
- [主题 CSS 变量](api/theming.md)

## 自定义 UI / 插件开发

- [自定义 UI 指南](custom-ui/README.md) — 自定义 UI 开发（快速入门、设计、模板、高级）
- [插件开发指南](plugin-development/getting-started.md) — 扩展开发入门
- [清单参考](plugin-development/manifest-reference.md) — extension.json 规范

## 安装

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## 历史文档

以下是过去的实现备忘录/热修复记录（位于 `archive/docs_history/`）。

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — v2.5.4 时代的调试指导
- `DARK_MODE_TAGS_IMPROVEMENT.md` — 暗模式标签改进建议（已实现）
- `EXTENSION_DRAFT.md` — 扩展系统初期草稿（plugin-development/ 中有后续）
