# Documentation Hub

이 파일을 "문서 입구(정규 허브)"로 사용하세요.

**최종 업데이트**: 2026-05-13

## Important

- Project README: [`../../README.ko.md`](../../README.ko.md)
- Changelog: [`../../CHANGELOG.ko.md`](../../CHANGELOG.ko.md)
- Master TODO (single source of truth): [`../../TODO.md`](../../TODO.md)

## Development Guidelines

개발 가이드라인은 `development/development_docs/`에 개별 파일로 배치되어 있습니다.

- **[TODO Rules](TODO_RULES.md)** — TODO 작성 규칙 (P0/P1/P2/P3 + 카테고리 필수)

### 주요 문서 (`development/development_docs/`)

| 문서 | 내용 |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | 300줄에서 검토 시작, 500줄에서 분할 필수 |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | feature-unit 디렉토리, 100-250줄이 이상적 |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | 3계층 방어 모델 (정적/파싱/런타임 검증) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` 통일, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | 모든 모듈 입구 목록 |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | 6가지 사고 지점 방지 전략 |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Tier A/B/C 버튼 설계 |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Explorer/Library 하이브리드 패턴 |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | 문서 배치 규칙 |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI 퍼즈/번인 테스트 |

### 기타 개발 문서

| 문서 | 내용 |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | AI 주도 개발의 설계 원칙 |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | 배치 작업 규약 |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | 확장 기능 훅 라이프사이클 |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | 재사용 가능한 UI 위젯 목록 |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI 프롬프트 구문 사양 |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | 아카이브 파일명 인코딩 |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API 이미지 형식 호환성 표 |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA 라운드 결과 · 미해결 과제 |

### 개발 로그 · 사양서

| 문서 | 내용 |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP 개발 로그 |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX 멀티백엔드 개발 로그 |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo 디바이스 제어 |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | 채팅 로그 확장 사양 |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri 데스크톱 통합 |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Freeze & Pull-back 확장 기능 사양 |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | 비디오 메타데이터 v2 계획 (Draft) |

## Import Paths

모든 import는 실제 모듈 경로를 직접 사용합니다. 별칭 메커니즘은 제거되었습니다.

**주요 경로 예시:**
- `core.services_core.db_api` — DB 접근 (이전 `core.db`)
- `core.configuration.api` — 설정 관리 (이전 `core.config`)
- `core.extensions_core.runtime` — 확장 기능 런타임 (이전 `core.extensions`)
- 새로운 기능은 `core/<feature>_core/` 디렉토리에 직접 추가

## Troubleshooting & Operations

- Debug playbook: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Common errors (레거시): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / 2바이트 문자 인코딩 함정: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- 이스케이프 괄호 파싱 오류: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| 문서 | 상태 | 내용 |
|---|---|---|
| [MCP 연동 가이드](features/mcp-integration-guide.md) | 현행 | LLM에서 yu_ai_manager 조작 |
| [NovelAI V4](features/novelai-v4.md) | 현행 | NovelAI V4 프롬프트 형식 · 캐릭터별 네거티브 대응 |
| [Hailo 시맨틱 검색](features/hailo-semantic-search.md) | 구현됨 → ONNX 마이그레이션 | Hailo-10H CLIP 구현 설명서 |
| [Danbooru 태그 자동 생성](features/danbooru-tag-gen-spec.md) | 구현됨 (v2.77.0) | WD-Tagger + VLM 2단 구조 |
| [텍스트 · 채팅 로그 관리](features/text-chatlog-management-spec.md) | 현행 | Chatlog 가져오기 · FTS 검색 |
| [QR 프로토콜 v1](features/qr-protocol-v1.md) | 현행 | LAN 공유용 QR 코드 |
| [정규표현식 검색 벤치마크](features/regex-search-benchmark.md) | 현행 | Regex 성능 |
| [브라우저 호환성](features/browser-compatibility.md) | 현행 | 지원 브라우저 목록 |

## API Reference

- [API 개요 (인증 · CSRF · 레이트 제한)](api/README.md)
- [검색 API](api/search.md)
- [파일 API](api/files.md)
- [스캔 API](api/scan.md)
- [SSE 이벤트](api/events.md)
- [테마 CSS 변수](api/theming.md)

## Custom UI / Plugin Development

- [Custom UI 가이드](custom-ui/README.md) — 커스텀 UI 개발 (quickstart, design, templates, advanced)
- [Plugin 개발 가이드](plugin-development/getting-started.md) — 확장 기능 개발 입문
- [매니페스트 레퍼런스](plugin-development/manifest-reference.md) — extension.json 사양

## Installation

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historical Docs

다음은 과거의 구현 메모/긴급 수정 기록입니다 (`archive/docs_history/`에 배치).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — v2.5.4 시대의 디버그 설명서
- `DARK_MODE_TAGS_IMPROVEMENT.md` — 다크 모드 태그 개선 제안 (구현됨)
- `EXTENSION_DRAFT.md` — Extension 시스템 초기 드래프트 (plugin-development/에 후속)
