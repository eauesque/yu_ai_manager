# Documentation Hub

Use this file as your "documentation entry point (canonical hub)".

**Last Updated**: 2026-05-13

## Important

- Project README: [`../../README.md`](../../README.md)
- Changelog: [`../../CHANGELOG.md`](../../CHANGELOG.md)
- Master TODO (single source of truth): [`../../TODO.md`](../../TODO.md)

## Development Guidelines

Development guidelines are organized as individual files in `development/development_docs/`.

- **[TODO Rules](TODO_RULES.md)** — TODO writing conventions (P0/P1/P2/P3 + category required)

### Key Documentation (`development/development_docs/`)

| Document | Description |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Start considering split at 300 lines, split required at 500 lines |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | feature-unit directory, 100-250 lines is ideal |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Three-layer defense model (static/parse/runtime validation) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | Unified `api_error()`, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Complete module entry point index |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Prevention strategies for 6 accident points |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Tier A/B/C button design |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Explorer/Library hybrid pattern |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Document placement rules |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI fuzz/burn-in testing |

### Other Development Documentation

| Document | Description |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Design principles for AI-driven development |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Batch operation conventions |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Extension hook lifecycle |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Reusable UI widgets index |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI prompt syntax specification |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Archive filename encoding |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API image format compatibility table |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA round results and remaining issues |

### Development Logs & Specifications

| Document | Description |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP development log |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX multi-backend development log |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo device control |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Enhanced chatlog specification |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri desktop integration |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Freeze & Pull-back extension specification |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Video metadata v2 plan (Draft) |

## Import Paths

All imports use direct module paths. Alias mechanisms have been removed.

**Key path examples:**
- `core.services_core.db_api` — DB access (formerly `core.db`)
- `core.configuration.api` — Configuration management (formerly `core.config`)
- `core.extensions_core.runtime` — Extension runtime (formerly `core.extensions`)
- New features are added directly to `core/<feature>_core/` directory

## Troubleshooting & Operations

- Debug playbook: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Common errors (legacy): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / multi-byte character encoding pitfalls: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Escaped bracket parse errors: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| Document | Status | Description |
|---|---|---|
| [MCP Integration Guide](features/mcp-integration-guide.md) | Current | Control YU AI Manager from LLM |
| [NovelAI V4](features/novelai-v4.md) | Current | NovelAI V4 prompt format and character-specific negative handling |
| [Hailo Semantic Search](features/hailo-semantic-search.md) | Implemented → ONNX Migration | Hailo-10H CLIP implementation guide |
| [Danbooru Tag Auto-generation](features/danbooru-tag-gen-spec.md) | Implemented (v2.77.0) | WD-Tagger + VLM two-stage approach |
| [Text & Chatlog Management](features/text-chatlog-management-spec.md) | Current | Chatlog import and FTS search |
| [QR Protocol v1](features/qr-protocol-v1.md) | Current | QR code for LAN sharing |
| [Regex Search Benchmark](features/regex-search-benchmark.md) | Current | Regex performance |
| [Browser Compatibility](features/browser-compatibility.md) | Current | Supported browsers list |

## API Reference

- [API Overview (Auth, CSRF, Rate Limiting)](api/README.md)
- [Search API](api/search.md)
- [Files API](api/files.md)
- [Scan API](api/scan.md)
- [SSE Events](api/events.md)
- [Theme CSS Variables](api/theming.md)

## Custom UI / Plugin Development

- [Custom UI Guide](custom-ui/README.md) — Custom UI development (quickstart, design, templates, advanced)
- [Plugin Development Guide](plugin-development/getting-started.md) — Extension development introduction
- [Manifest Reference](plugin-development/manifest-reference.md) — extension.json specification

## Installation

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historical Docs

The following are legacy implementation notes and hotfix records (located in `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Debug instructions from v2.5.4 era
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Dark mode tags improvement proposal (implemented)
- `EXTENSION_DRAFT.md` — Initial Extension system draft (successor in plugin-development/)
