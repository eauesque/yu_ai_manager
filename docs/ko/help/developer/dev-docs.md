# 개발 문서 인덱스

내부 설계 문서, 기술 참조, 개발 로그의 인덱스입니다.
모든 파일은 `docs/development/development_docs/`에 있습니다.

MCP의 `source_read` 도구를 통해 직접 읽을 수도 있습니다.

---

## 설계 및 아키텍처

| 문서 | 설명 |
|------|------|
| DESIGN_PHILOSOPHY | 설계 철학 -- 프로젝트 전반의 원칙과 결정 기준 |
| MODULE_ORGANIZATION_GUIDELINES | 모듈 구성 가이드라인 |
| CODE_SIZE_GUIDELINES | 코드 크기 가이드라인 (파일 분할 기준) |
| ENTRYPOINT_MAP | 엔트리포인트 맵 |
| DOCUMENT_LIFECYCLE | 문서 라이프사이클 정책 |
| UI_STATE_SPEC | UI 상태 사양 (Explorer/Library 하이브리드) |
| NOTIFICATION_PROGRESS_DESIGN | 알림 및 진행 상황 표시 설계 |

## API 및 배치 처리

| 문서 | 설명 |
|------|------|
| API_RESPONSE_GUIDELINES | API 응답 형식 가이드라인 |
| BATCH_API_STANDARD | 배치 API 표준 |
| ERROR_HANDLING | 오류 처리 정책 |

## Extension 시스템

| 문서 | 설명 |
|------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | 삼권분립 보안 모델 사양 |
| EXTENSION_SANDBOX_SPEC | 샌드박스 및 권한 사양 |
| EXTENSION_HOOKS_SPEC | Extension Hooks 사양 |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator 사양 |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core -> Extension 마이그레이션 사양 |

## AI 및 Agent 통합

| 문서 | 설명 |
|------|------|
| AGENT_INTEGRATION_DESIGN | AI Agent 통합 설계 가이드 |
| AGENT_SAFETY_GATEWAY_SPEC | AI Agent Safety Gateway 사양 |
| AI_ANALYSIS_LANGUAGE | AI 분석 응답 언어 사양 |
| MCP_DEBUG_TOOLS | MCP 디버그 도구 사양 |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM 통합 함정과 해결책 |
| OPENAI_COMPAT_API_DEVLOG | OpenAI 호환 API 개발 로그 |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing 및 OCR 설계 사양 |
| VISION_API_IMAGE_FORMATS | Vision API 이미지 형식 지원 표 |
| ai-driven-development-principles | AI 주도 개발 원칙 |

## 데이터베이스 및 성능

| 문서 | 설명 |
|------|------|
| SQLITE_READONLY_SEPARATION | SQLite 읽기/쓰기 분리 패턴 |
| LARGE_SCALE_QUERY_OPTIMIZATION | 대규모 DB (280K 파일) 쿼리 최적화 |

## 프론트엔드 및 UI

| 문서 | 설명 |
|------|------|
| UI_AUDIT_GUIDE | 종합 UI 감사 가이드 |
| UI_BUTTON_PRIORITY_GUIDELINES | 버튼 우선순위 가이드라인 (GC 컨트롤러 스타일) |
| REUSABLE_UI_WIDGETS | 재사용 가능한 UI 위젯 통합 가이드 |
| VIRTUAL_SCROLL_PITFALLS | 가상 스크롤 함정 및 알려진 버그 |
| IMAGE_DISPLAY_OPTIMIZATION | 이미지 표시 최적화 기술 참조 |
| MODAL_LOADING_OPTIMIZATION | 상세 모달 로딩 최적화 |
| MODAL_MEDIA_LIFECYCLE | 모달 미디어 라이프사이클 관리 |
| CONTAINER_VIEW_PERFORMANCE | 컨테이너 뷰 성능 최적화 |
| BROWSER_CONNECTION_SATURATION | 브라우저 연결 포화로 인한 누락 결과 |

## 동영상 처리

| 문서 | 설명 |
|------|------|
| VIDEO_STREAMING_ARCHITECTURE | 동영상 스트리밍 아키텍처 |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | 동영상 성능 최적화 전체 이력 |
| VIDEO_METADATA_V2_PLAN | Video Metadata v2 계획 (초안) |

## 파일 및 아카이브 처리

| 문서 | 설명 |
|------|------|
| NESTED_ZIP_HANDLING | 중첩 ZIP 처리 설계 및 함정 |
| ZIP_SCAN_PERFORMANCE | ZIP/7z 스캔 성능 최적화 |
| ENCODING_FALLBACK | 아카이브 파일명 인코딩 폴백 사양 |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD / NAI 프롬프트 구문 사양 |

## 크로스 플랫폼 및 인프라

| 문서 | 설명 |
|------|------|
| CROSS_PLATFORM_ISSUES | 크로스 플랫폼 차이 가이드 |
| DRAG_TO_SHARE_CROSS_PLATFORM | 드래그 앤 드롭 크로스 플랫폼 지원 |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio 이벤트 루프 블로킹 수정 |
| MODULE_SAFETY | 모듈 안전 로딩 설계 |
| DOCKER_SETUP | Docker 설정 가이드 |
| TAURI_DESKTOP_APP | Tauri 데스크톱 앱 개발 가이드 |

## 마이그레이션

| 문서 | 설명 |
|------|------|
| QUART_MIGRATION_DEVLOG | Flask -> Quart (ASGI) 마이그레이션 기술 참조 |
| CHATLOG_ENHANCED_SPEC | 채팅 로그 강화 사양 |

## 테스트 및 품질

| 문서 | 설명 |
|------|------|
| FUZZ_BURN_IN_TEST | Fuzz / Burn-in 테스트 가이드 |
| QA_HANDOFF | QA 인수인계 문서 |
| yu-ai-manager-qa-agent-prompt | QA 에이전트 시스템 프롬프트 |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | 사고 포인트 및 공통 레이어 속도 가이드 |
| BUG_VIDEO_AI_ANALYZED_FILTER | 버그 기록: Video + AI analyzed 필터 |

## 릴리스 및 번역

| 문서 | 설명 |
|------|------|
| RELEASE_PROCEDURE | 릴리스 절차 |
| TRANSLATION_STYLE_GUIDE | 일본어 -> 영어 번역 스타일 가이드 |
