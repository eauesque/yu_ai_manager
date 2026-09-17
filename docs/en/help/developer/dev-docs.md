# Development Documents Index

An index of internal design documents, technical references, and development logs.
All files are located in `docs/development/development_docs/`.

You can also read them directly via MCP's `source_read` tool.

---

## Design & Architecture

| Document | Description |
|----------|-------------|
| DESIGN_PHILOSOPHY | Design philosophy — project-wide principles and decision criteria |
| MODULE_ORGANIZATION_GUIDELINES | Module organization guidelines |
| CODE_SIZE_GUIDELINES | Code size guidelines (file splitting criteria) |
| ENTRYPOINT_MAP | Entrypoint map |
| DOCUMENT_LIFECYCLE | Documentation lifecycle policy |
| UI_STATE_SPEC | UI state specification (Explorer/Library hybrid) |
| NOTIFICATION_PROGRESS_DESIGN | Notification and progress display design |

## API & Batch Processing

| Document | Description |
|----------|-------------|
| API_RESPONSE_GUIDELINES | API response format guidelines |
| BATCH_API_STANDARD | Batch API standard |
| ERROR_HANDLING | Error handling policy |

## Extension System

| Document | Description |
|----------|-------------|
| EXTENSION_TRIAS_POLITICA_SPEC | Trias Politica security model specification |
| EXTENSION_SANDBOX_SPEC | Sandbox & Permission specification |
| EXTENSION_HOOKS_SPEC | Extension Hooks specification |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator spec |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core → Extension migration spec |

## AI & Agent Integration

| Document | Description |
|----------|-------------|
| AGENT_INTEGRATION_DESIGN | AI Agent integration design guide |
| AGENT_SAFETY_GATEWAY_SPEC | AI Agent Safety Gateway specification |
| AI_ANALYSIS_LANGUAGE | AI analysis response language specification |
| MCP_DEBUG_TOOLS | MCP debug tools specification |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM integration pitfalls and solutions |
| OPENAI_COMPAT_API_DEVLOG | OpenAI compatible API development log |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing & OCR design specification |
| VISION_API_IMAGE_FORMATS | Vision API image format support table |
| ai-driven-development-principles | AI-driven development principles |

## Database & Performance

| Document | Description |
|----------|-------------|
| SQLITE_READONLY_SEPARATION | SQLite read/write separation pattern |
| LARGE_SCALE_QUERY_OPTIMIZATION | Large-scale DB (280K files) query optimization |

## Frontend & UI

| Document | Description |
|----------|-------------|
| UI_AUDIT_GUIDE | Comprehensive UI audit guide |
| UI_BUTTON_PRIORITY_GUIDELINES | Button priority guidelines (GC controller style) |
| REUSABLE_UI_WIDGETS | Reusable UI widgets integration guide |
| VIRTUAL_SCROLL_PITFALLS | Virtual scroll pitfalls and known bugs |
| IMAGE_DISPLAY_OPTIMIZATION | Image display optimization technical reference |
| MODAL_LOADING_OPTIMIZATION | Detail modal loading optimization |
| MODAL_MEDIA_LIFECYCLE | Modal media lifecycle management |
| CONTAINER_VIEW_PERFORMANCE | Container view performance optimization |
| BROWSER_CONNECTION_SATURATION | Browser connection saturation causing missing results |

## Video Processing

| Document | Description |
|----------|-------------|
| VIDEO_STREAMING_ARCHITECTURE | Video streaming architecture |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Complete video performance optimization history |
| VIDEO_METADATA_V2_PLAN | Video Metadata v2 plan (draft) |

## File & Archive Processing

| Document | Description |
|----------|-------------|
| NESTED_ZIP_HANDLING | Nested ZIP handling design and pitfalls |
| ZIP_SCAN_PERFORMANCE | ZIP/7z scan performance optimization |
| ENCODING_FALLBACK | Archive filename encoding fallback specification |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD / NAI prompt syntax specification |

## Cross-Platform & Infrastructure

| Document | Description |
|----------|-------------|
| CROSS_PLATFORM_ISSUES | Cross-platform differences guide |
| DRAG_TO_SHARE_CROSS_PLATFORM | Drag & drop cross-platform support |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio event loop blocking fix |
| MODULE_SAFETY | Module safe-loading design |
| DOCKER_SETUP | Docker setup guide |
| TAURI_DESKTOP_APP | Tauri desktop app development guide |

## Migration

| Document | Description |
|----------|-------------|
| QUART_MIGRATION_DEVLOG | Flask → Quart (ASGI) migration technical reference |
| CHATLOG_ENHANCED_SPEC | Chat log enhanced specification |

## Testing & Quality

| Document | Description |
|----------|-------------|
| FUZZ_BURN_IN_TEST | Fuzz / Burn-in test guide |
| QA_HANDOFF | QA handoff document |
| yu-ai-manager-qa-agent-prompt | QA agent system prompt |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Accident points & common layer speed guide |
| BUG_VIDEO_AI_ANALYZED_FILTER | Bug record: Video + AI analyzed filter |

## Release & Translation

| Document | Description |
|----------|-------------|
| RELEASE_PROCEDURE | Release procedure |
| TRANSLATION_STYLE_GUIDE | Japanese → English translation style guide |
