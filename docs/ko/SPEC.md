# Yu AI Manager — 전체 명세서

> **대상 독자**: Claude Desktop 등의 AI 에이전트  
> **버전**: v4.91.15  
> **업데이트**: 2026-04-19

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [기술 스택](#2-기술-스택)
3. [아키텍처 개요](#3-아키텍처-개요)
4. [인증 및 보안](#4-인증-및-보안)
5. [REST API エンドポイント](#5-rest-api-エンドポイント)
6. [MCP Server](#6-mcp-server)
7. [SSE Events](#7-sse-events)
8. [DB Schema](#8-db-schema)
9. [확장（Extensions）](#9-확장extensions)
10. [설정（config.json）](#10-설정configjson)
11. [파일 구조](#11-파일-구조)
12. [개발 규약](#12-개발-규약)

---

## 1. 프로젝트 개요

**Yu AI Manager**는 AI 생성 이미지·동영상·오디오·텍스트의 로컬 라이브러리 관리 시스템입니다.  
엣지 퍼스트·클라우드 비의존을 설계 철학으로 하여, 로컬/LAN에서 완결되는 것을 우선합니다.

### 주요 기능

| 기능 | 설명 |
|------|------|
| 라이브러리 관리 | 이미지/동영상/오디오/텍스트의 스캔·태그·검색 |
| 메타데이터 추출 | A1111 / ComfyUI / NovelAI 생성 파라미터 자동 추출 |
| AI 분석 | Claude / OpenAI / Ollama / Hailo VLM에 의한 이미지 분석 |
| 시맨틱 검색 | CLIP (ONNX/CoreML) + Hailo에 의한 의미 검색 |
| Bridge 연동 | Stable Diffusion / ComfyUI / NovelAI로의 생성 요청 |
| LLM Router | Ollama / OpenAI 호환 백엔드로의 통합 라우팅 |
| Agent Safety | Kill Switch / Circuit Breaker / Approval Gate 등의 안전 기구 |
| LAN 협업 | mDNS에 의한 자동 발견 + 피어 간 공유 |
| MCP Server | Claude Desktop 등에서 직접 조작 가능한 180+ 도구 |

---

## 2. 기술 스택

| 레이어 | 기술 |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (FTS5 전문 검색 + zstd 압축 BLOB) |
| Frontend | TypeScript + Vite 빌드 |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| 패키지 관리 | Python: `uv pip` / Node.js: `pnpm` |

### 포트 규약

- `5000–5099`: 프로덕션 앱 예약 대역（변경 금지）
- `5100+`: 테스트·디버그용（`scripts/find_port.py`로 빈 포트 자동 취득）

---

## 3. 아키텍처 개요

```
┌──────────────────────────────────────────────────┐
│  클라이언트 층                                     │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ 외부 도구 (API Key / LAN Peer)               │
├──────────────────────────────────────────────────┤
│  인증 층 (auth_chain.py)                          │
│  ├─ PIN / QuickLock (보스 락)                    │
│  ├─ API Key (Bearer / 스코프)                    │
│  └─ LAN 피어 신뢰 (mDNS 검증)                   │
├──────────────────────────────────────────────────┤
│  API 층                                           │
│  ├─ REST API (235+ 엔드포인트 / Quart Blueprint)  │
│  ├─ SSE 스트림 (/api/events/stream)              │
│  └─ MCP Server (180+ 도구)                       │
├──────────────────────────────────────────────────┤
│  서비스 층                                         │
│  ├─ TagDB (SQLite / Schema v53)                  │
│  ├─ Event Bus (SSE 브로드캐스터)                 │
│  ├─ LLM Router (복수 백엔드 통합)                │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo) │
│  ├─ Extensions (47 builtin)                      │
│  └─ File Services (스캔/서브/썸네일)             │
├──────────────────────────────────────────────────┤
│  Agent Safety 층                                  │
│  ├─ Kill Switch          ├─ Budget Tracker        │
│  ├─ Circuit Breaker      ├─ Approval Gate         │
│  ├─ Scope Fence          ├─ Undo Engine           │
│  ├─ Anomaly Detector     └─ Audit Bureau          │
└──────────────────────────────────────────────────┘
```

### 모듈 의존 방향

```
routes/ → core/services_core/ → core/tagdb_core/ → SQLite
routes/ → core/web/ (인증)
mcp_server/ → routes/ 경유 또는 코어 직접 호출
extensions/ → core/extensions_core/ (라이프사이클 관리)
```

---

## 4. 인증 및 보안

### 인증 체인 (core/web/auth_chain.py)

요청마다 다음 순서로 평가:

1. **정적 파일 바이패스** — `/static/`, `/favicon.ico`, `/help/*`
2. **MCP 바이패스** — `/mcp` (MCP 자체의 인증)
3. **LLM Router 바이패스** — `/v1/` (루프백 시만)
4. **LAN Share 바이패스** — `/s/<token>` (공유 토큰)
5. **LAN 피어 신뢰** — mDNS 검증된 피어는 PIN 불필요
6. **API 키 인증** — `Authorization: Bearer <key>` (스코프 검증)
7. **QuickLock 체크** — 잠금 시 `/api/lock/unlock`만 허용
8. **PIN 체크** — 브라우저 세션 인증

### API 키 스코프

| 스코프 | 권한 |
|---------|------|
| `read` | 읽기 전반 |
| `write` | 파일·설정 쓰기 |
| `tag.write` | 태그 추가·삭제 |
| `collection.write` | 컬렉션 관리 |
| `annotate` | 어노테이션 |
| `scan` | 스캔 작업 |
| `admin` | 관리자（전체 작업） |

### QuickLock / Boss Mode

- PIN은 PBKDF2-SHA256 (600k 반복)으로 해시
- 속도 제한: 최대 5회 실패 시 60초 잠금
- `/api/lock/status`로 잠금 상태 확인（인증 불필요）
- `/api/lock/unlock`으로 해제（PIN 필수）

### 시크릿 관리

- 1Password 통합（`op://vault/item/field` 참조 형식）
- Bitwarden 통합
- 설정값은 Fernet 대칭 암호화（`enc:...` 프리픽스）

---

## 5. REST API エンドポイント

기본 URL: `http://localhost:5000`（기본값）

### Agent Safety

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/agent/status` | Kill Switch + CB + Budget 통합 상태 |
| POST | `/api/agent/kill` | Kill Switch 활성화 |
| POST | `/api/agent/resume` | Kill Switch 비활성화 |
| GET | `/api/agent/circuit-breaker` | Circuit Breaker 상태 |
| POST | `/api/agent/circuit-breaker/reset` | CB 리셋 |
| GET | `/api/agent/budget` | 예산 잔량 |
| POST | `/api/agent/budget/reset` | 예산 리셋 |
| GET | `/api/agent/journal` | 액션 저널 검색 |
| GET | `/api/agent/journal/stats` | 저널 통계 |
| GET | `/api/agent/approval` | 승인 대기 요청 목록 |
| POST | `/api/agent/approval/<request_id>` | 승인/거부 |
| GET | `/api/agent/approval/history` | 승인 이력 |
| POST | `/api/agent/undo/<int:journal_id>` | 언두 실행 |
| GET | `/api/agent/undoable` | 언두 가능 저널 |
| GET | `/api/agent/anomaly` | 이상 감지 알림 |
| GET | `/api/agent/audit` | 감사 로그 |
| GET | `/api/agent/scope` | 스코프 목록 |
| GET | `/api/agent/scope/<session_id>` | 세션 스코프 |
| POST | `/api/agent/scope/<session_id>` | 스코프 갱신 |
| DELETE | `/api/agent/scope/<session_id>` | 스코프 삭제 |
| GET | `/api/agent/auto-approve` | 자동 승인 규칙 |
| POST | `/api/agent/auto-approve` | 규칙 추가 |
| DELETE | `/api/agent/auto-approve/<int:index>` | 규칙 삭제 |
| GET | `/api/agent/tool-levels` | 도구 안전 레벨 |

### AI 분석

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/analysis/config` | 설정 취득 |
| POST | `/api/analysis/config` | 설정 갱신 |
| GET | `/api/analysis/available-engines` | 사용 가능 엔진 목록 |
| GET | `/api/analysis/ollama/models` | Ollama 모델 목록 |
| POST | `/api/analysis/ollama/test` | 연결 테스트 |
| POST | `/api/analysis/analyze/<int:file_id>` | 파일 분석 |
| GET | `/api/analysis/result/<int:file_id>` | 분석 결과 |
| POST | `/api/analysis/batch` | 배치 분석 |
| POST | `/api/analysis/batch/cancel` | 배치 취소 |
| GET | `/api/analysis/servers` | 분석 서버 목록 |
| POST | `/api/analysis/servers` | 서버 추가 |
| PUT | `/api/analysis/servers/<server_id>` | 서버 갱신 |
| DELETE | `/api/analysis/servers/<server_id>` | 서버 삭제 |
| GET | `/api/analysis/servers/discovered` | 자동 발견 서버 |
| POST | `/api/analysis/servers/discovered/register` | 등록 |

### 파일·스캔

| 메서드 | 경로 | 설명 |
|---------|------|------|
| POST | `/api/scan/start` | 스캔 시작 |
| POST | `/api/scan/cancel` | 취소 |
| POST | `/api/scan/resume` | 재개 |
| GET | `/api/scan/status` | 상태 |
| GET | `/api/scan/queue` | 큐 목록 |
| DELETE | `/api/scan/queue/<queue_id>` | 큐 삭제 |
| POST | `/api/scan/queue/clear` | 큐 클리어 |
| GET | `/api/scan/history` | 스캔 이력 |
| GET | `/api/scan-errors` | 스캔 에러 |
| POST | `/api/scan-errors/<int:error_id>/resolve` | 에러 해결 |
| GET | `/api/scanned-roots` | 스캔된 루트 |
| POST | `/api/scanned-roots/purge` | 루트 삭제 |

### 태그·즐겨찾기·평점

| 메서드 | 경로 | 설명 |
|---------|------|------|
| POST | `/api/tags/add` | 태그 추가 |
| POST | `/api/tags/remove` | 태그 삭제 |
| GET | `/api/tags/list` | 태그 목록 |
| POST | `/api/favorites/toggle` | 즐겨찾기 토글 |
| GET | `/api/favorites/check` | 즐겨찾기 확인 |
| GET | `/api/favorites/list` | 즐겨찾기 목록 |
| GET | `/api/ratings/get` | 평점 취득 |
| POST | `/api/ratings/set` | 평점 설정 |
| POST | `/api/ratings/batch-set` | 배치 설정 |
| GET | `/api/ratings/stats` | 통계 |

### 컬렉션

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/collections` | 컬렉션 목록 |
| POST | `/api/collections` | 생성 |
| PUT | `/api/collections/<int:collection_id>` | 갱신 |
| DELETE | `/api/collections/<int:collection_id>` | 삭제 |
| POST | `/api/collections/reorder` | 정렬 변경 |
| POST | `/api/collections/<int:collection_id>/batch-add` | 배치 추가 |
| POST | `/api/collections/<int:collection_id>/batch-remove` | 배치 삭제 |
| GET | `/api/collections/<int:collection_id>/export/csv` | CSV 내보내기 |

### LLM Router

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/llm_router/status` | 상태 |
| POST | `/api/llm_router/refresh` | 리프레시 |
| POST | `/api/llm_router/backends/<alias>/enable` | 백엔드 활성화 |
| POST | `/api/llm_router/backends/<alias>/disable` | 백엔드 비활성화 |
| POST | `/v1/chat/completions` | OpenAI 호환 채팅 |
| GET | `/v1/models` | 모델 목록 |

### 시스템·서버 정보

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/system/inference-info` | 추론 엔진 정보 |
| GET | `/api/mdns/identity` | mDNS 아이덴티티 |
| GET | `/api/mdns/peers` | LAN 피어 목록 |
| GET | `/api/logs/recent` | 최근 로그 |
| GET | `/api/logs/stream` | 로그 SSE 스트림 |
| GET | `/api/jobs/status` | 잡 상태 |
| GET | `/api/events/stream` | SSE 이벤트 스트림 |
| GET | `/api/events/info` | SSE 연결 정보 |

### 설정·시크릿

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET/POST | `/api/settings/llm-endpoints` | LLM 엔드포인트 관리 |
| GET/POST | `/api/settings/secrets/*` | 시크릿 관리 |
| GET | `/api/settings/bw-status` | Bitwarden 상태 |
| GET | `/api/settings/op-status` | 1Password 상태 |

### 도움말

| 메서드 | 경로 | 설명 |
|---------|------|------|
| GET | `/api/help/toc` | 목차 |
| GET | `/api/help/content/<section>` | 컨텐츠 |
| GET | `/api/help/search` | 검색 |

---

## 6. MCP Server

### 연결

```
Transport: stdio 또는 SSE
엔드포인트: /mcp (SSE 모드 시)
```

### 도구 그룹（180+ 도구）

| 그룹 | 등록 함수 | 주요 도구 |
|---------|---------|-----------|
| **Agent Safety** | `register_agent_safety_tools` 등 | kill_switch, circuit_breaker, budget, journal, approval, scope, undo, anomaly, audit |
| **Analysis** | `register_analysis_tools` 등 | analyze_file, batch_analyze, analysis_config, analysis_servers |
| **Batch** | `register_batch_tools` 등 | batch_scan, batch_annotate, batch_operation |
| **File Management** | `register_misc_file_tools` 등 | file_meta, duplicate_detect, dnd_register, download |
| **Search** | `register_search_tools` 등 | search, cross_search, collection_search, semantic_search |
| **LLM** | `register_llm_tools` 등 | llm_chat, llm_endpoint, llm_router |
| **Bridge - NAI** | `register_nai_bridge_tools` | nai_generate, nai_config |
| **Bridge - SD** | `register_sd_bridge_tools` | sd_generate, sd_config |
| **Bridge - ComfyUI** | `register_comfyui_bridge_tools` | comfyui_generate, comfyui_workflow |
| **Bridge - SD↔NAI** | `register_sd_nai_convert_tools` | convert_prompt |
| **Extensions** | `register_extension_tools` 등 | extension_list, extension_enable, extension_disable |
| **Scan Roots** | `register_scan_roots_tools` 등 | scan_root_add, scan_root_remove, scan_start |
| **Hailo GenAI** | `register_hailo_genai_tools` 등 | hailo_generate, hailo_benchmark |
| **Hailo Tagger** | `register_hailo_tagger_tools` | hailo_tag |
| **YOLO** | `register_yolo_detect_tools` 등 | yolo_detect, yolo_stream |
| **Semantic** | `register_semantic_tools` | semantic_search, semantic_index |
| **WD-Tagger** | `register_wd_tagger_tools` | wd_tag, wd_batch_tag |
| **OCR** | `register_ocr_tools` | ocr_extract |
| **Chatlog** | `register_chatlog_tools` | chatlog_save, chatlog_search |
| **Prompt Library** | `register_prompt_library_tools` | prompt_save, prompt_search |
| **Prompt Sim** | `register_prompt_sim_tools` | prompt_simulate, wildcard_expand |
| **LoRA Dataset** | `register_lora_dataset_tools` | lora_dataset_manage |
| **Stats** | `register_stats_tools` 등 | stats_summary, monthly_report, trophy |
| **GitHub** | `register_github_tools` 등 | github_issues, github_queue, github_triage |
| **SNS** | `register_sns_share_tools` 등 | sns_post, bluesky_post |
| **Utility** | `register_debug_tools` 등 | debug_query, help_search, settings_get |

### Safety 인터셉터

모든 MCP 도구 호출은 다음을 자동 체크:
1. Kill Switch — 활성 시 전체 도구 실행 거부
2. Circuit Breaker — 연속 에러 시 자동 차단
3. Budget Tracker — 예산 초과 시 경고/정지
4. Approval Gate — `admin` 스코프 작업은 인간 승인 대기
5. Scope Fence — 세션 스코프 외 접근 거부

---

## 7. SSE Events

### 연결

```
GET /api/events/stream?types=<event1>,<event2>,...
Content-Type: text/event-stream
```

`types` 생략 시 전체 이벤트 수신.

### 이벤트 목록

**스캔**

| 이벤트 | 설명 |
|---------|------|
| `scan.start` | 스캔 시작 |
| `scan.progress` | 진행（processed/total） |
| `scan.complete` | 완료 |
| `scan.error` | 에러 |
| `scan.queued` | 큐 등록 |

**파일 작업**

| 이벤트 | 설명 |
|---------|------|
| `favorite.add` / `favorite.remove` | 즐겨찾기 |
| `tag.add` / `tag.remove` | 태그 |
| `rating.set` / `rating.clear` | 평점 |
| `annotation.set` / `annotation.delete` | 어노테이션 |
| `collection.create` / `collection.delete` | 컬렉션 |

**생성**

| 이벤트 | 설명 |
|---------|------|
| `generation.submit` | 생성 요청 |
| `generation.progress` | 진행 |
| `generation.complete` | 완료 |
| `generation.error` | 에러 |
| `generation.cancel` | 취소 |

**분석·추론**

| 이벤트 | 설명 |
|---------|------|
| `analysis.complete` | 분석 완료 |
| `batch_analysis.complete` | 배치 완료 |
| `semantic_index.start/progress/complete` | 인덱스 |
| `yolo_detect.start/progress/complete` | 물체 감지 |
| `wd_tagger.complete` | WD-Tagger 완료 |
| `ocr.complete` | OCR 완료 |

**Agent Safety**

| 이벤트 | 설명 |
|---------|------|
| `agent.killed` | Kill Switch 활성 |
| `agent.resumed` | 재개 |
| `agent.circuit_open` | Circuit Breaker 개방 |
| `agent.circuit_closed` | 폐쇄 |
| `agent.budget_warning` | 예산 경고 |
| `agent.budget_exhausted` | 예산 소진 |

**LAN 협업**

| 이벤트 | 설명 |
|---------|------|
| `peer.discovered` | 피어 발견 |
| `peer.online` / `peer.offline` | 상태 변화 |
| `sync.file_changed` / `sync.file_received` | 파일 동기화 |
| `sync.conflict` | 충돌 |

**기타**

| 이벤트 | 설명 |
|---------|------|
| `scheduler.job_executed` | 스케줄러 잡 실행 |
| `backup.complete` / `backup.error` | 백업 |
| `config.scan_roots_changed` | 스캔 루트 변경 |
| `watcher.started` / `watcher.stopped` | 파일 감시 |
| `webhook.received` | Webhook 수신 |
| `github_queue.new_issues` | GitHub 신규 Issue |
| `bsky_queue.new_notifications` | Bluesky 신규 알림 |
| `chatlog_reprocess.start/progress/complete` | 채팅 로그 재처리 |
| `fpb.start/progress/complete/error` | Freeze & Pull-back |

---

## 8. DB Schema

**DB 파일**: `tags.db`（최상위 디렉토리, `--db`로 지정 가능）  
**Schema 버전**: 53  
**읽기/쓰기 분리**: GET 계열은 `get_readonly_db()` 사용 필수

### 주요 테이블

```sql
-- 파일
files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  mtime INTEGER,
  size INTEGER,
  hash TEXT,
  is_deleted INTEGER DEFAULT 0,         -- 소프트 삭제
  parser_version INTEGER DEFAULT 1,
  meta_source TEXT,
  is_zip_member INTEGER DEFAULT 0,
  extracted_from_zip TEXT,
  extracted_from_internal TEXT,
  extraction_date INTEGER,
  extracted_to_file_id INTEGER,
  width INTEGER,
  height INTEGER,
  file_ext TEXT GENERATED ALWAYS AS     -- 자동 생성
    (lower(substr(path, instr(path,'.',-1)+1))) STORED
)

-- 태그 사전
tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,                        -- "namespace:tag" 형식
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
)

-- 파일↔태그 관계
file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL DEFAULT 1.0,              -- 태그 가중치
  source TEXT DEFAULT 'meta',           -- 'meta'|'manual'|'ai'|'wd'
  PRIMARY KEY (file_id, tag_id)
)

-- 생성 파라미터
templates (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL UNIQUE,
  raw_prompt TEXT,
  raw_negative TEXT,
  format TEXT,                           -- 'a1111'|'comfyui'|'nai'
  model_name TEXT,
  model_hash TEXT,
  char_positive TEXT,
  char_negative TEXT
)

-- 프롬프트 토큰
template_tokens (
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL,
  token_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  position INTEGER NOT NULL
)

-- 메타데이터 추출 상태
media_extract_state (
  file_id INTEGER PRIMARY KEY,
  cache_state TEXT DEFAULT 'none',       -- 'none'|'pending'|'done'|'error'
  metadata_schema_version INTEGER,
  metadata_extracted_at INTEGER,
  metadata_source TEXT,
  fingerprint_mtime INTEGER,
  fingerprint_hash TEXT,
  error_code TEXT,
  error_count INTEGER DEFAULT 0,
  next_retry_after INTEGER,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- 파일 캐시（썸네일 등）
cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                    -- 'thumbnail'|'preview'|'clip_emb'
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER DEFAULT 0,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- 즐겨찾기
favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER DEFAULT 1,
  added_at INTEGER,
  PRIMARY KEY (file_id, collection_id)
)

-- Schema 버전 관리
schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER,
  description TEXT
)

-- 확장 schema 버전
extension_schema_versions (
  extension_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  applied_at INTEGER,
  description TEXT,
  PRIMARY KEY (extension_name, version)
)

-- DB 메타 정보
db_meta (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER
)
```

### FTS5（전문 검색）

```sql
-- 프롬프트 전문 검색
templates_fts USING fts5 (
  content='templates',
  raw_prompt, raw_negative, model_name
)
```

주의: CJK 문자는 FTS5 미지원으로 LIKE 폴백을 사용.

### 주요 인덱스

```sql
idx_tags_tag_lower          -- 태그 대소문자 구분 없음
idx_files_deleted_mtime     -- 소프트 삭제 + mtime
idx_files_deleted_source    -- 소프트 삭제 + 소스
idx_file_tags_tag_id        -- 태그 ID 검색
idx_file_tags_source        -- 메타데이터 소스
idx_media_extract_cache_state -- 캐시 상태
idx_media_extract_next_retry  -- 재시도 대기
idx_files_hash              -- 해시（중복 감지）
idx_files_deleted_ext       -- 확장자 필터
```

---

## 9. 확장（Extensions）

### 구성

```
extensions/
  builtin-<name>/
    extension.json     # 메타데이터
    <name>_ext.py      # 엔트리 포인트
    templates/         # HTML 템플릿
    static/            # 정적 파일
```

### extension.json 포맷

```json
{
  "name": "builtin-analysis",
  "version": "1.0.0",
  "description": "AI 이미지 분석 엔진",
  "type": "general",
  "category": "ai",
  "entry": "analysis_ext.py",
  "has_blueprint": true,
  "core_shim": "analysis",
  "config": {
    "enabled": true,
    "priority": 150
  }
}
```

### 내장 확장 목록（47개）

| 확장명 | 카테고리 | 설명 |
|--------|---------|------|
| builtin-a1111 | parser | A1111 메타데이터 추출 |
| builtin-analysis | ai | AI 이미지 분석（Claude/OpenAI/Ollama） |
| builtin-annotations | utility | 어노테이션 관리 |
| builtin-audio-analysis | ai | 오디오 분석（Whisper） |
| builtin-auto-scan-watcher | utility | 파일 변경 자동 스캔 |
| builtin-backup | utility | DB/설정 백업 |
| builtin-chatlog | utility | 채팅 로그 관리 |
| builtin-clip-coreml | ai | CLIP 시맨틱 검색（macOS） |
| builtin-clip-onnx | ai | CLIP 시맨틱 검색（크로스 플랫폼） |
| builtin-clip-search | search | CLIP 검색 UI |
| builtin-comfyui | parser | ComfyUI 메타데이터 추출 |
| builtin-comfyui-bridge | bridge | ComfyUI API 연동 |
| builtin-cross-search | search | 텍스트 전문 검색 |
| builtin-debug-check | utility | 시스템 진단 |
| builtin-download | utility | URL/마그넷 링크 다운로드 |
| builtin-export | utility | CSV/JSON/ZIP 내보내기 |
| builtin-favorites-manager | utility | 즐겨찾기·컬렉션 |
| builtin-freeze-pullback | utility | 파일 복원 |
| builtin-github-integration | integration | GitHub Issue/PR 관리 |
| builtin-hailo-genai | ai | Hailo 생성 AI |
| builtin-hailo-semantic-search | search | Hailo 시맨틱 검색 |
| builtin-hailo-yolo-detect | ai | Hailo YOLO 물체 감지 |
| builtin-inference | ai | 원격 추론 관리 |
| builtin-lan-cowork | network | LAN 협업 |
| builtin-lan-share | network | LAN QR 공유 |
| builtin-lora-dataset-manager | utility | LoRA 데이터셋（kohya-ss 연동） |
| builtin-mcp-client | integration | 외부 MCP 서버 연결 |
| builtin-md-viewer | utility | Markdown 파일 표시 |
| builtin-nai-bridge | bridge | NovelAI API 연동 |
| builtin-novelai-v3 | parser | NovelAI v3 메타데이터 |
| builtin-novelai-v4 | parser | NovelAI v4 메타데이터 |
| builtin-ocr | ai | OCR 텍스트 추출 |
| builtin-prompt-library | utility | 프롬프트 관리·검색 |
| builtin-prompt-simulator | utility | 와일드카드 전개 |
| builtin-prompt-syntax | utility | Lora/제어 토큰 해석 |
| builtin-ratings | utility | 5단계 평가 |
| builtin-sd-nai-convert | utility | SD ↔ NAI 프롬프트 변환 |
| builtin-sd-webui-bridge | bridge | SD WebUI API 연동 |
| builtin-sns-share | integration | SNS 게시（Bluesky/Twitter） |
| builtin-speech-to-text | ai | 음성 인식 |
| builtin-stats | utility | 통계 대시보드 |
| builtin-tag-dictionary | utility | 태그 사전·설명 |
| builtin-trophy | utility | 마일스톤 달성 |
| builtin-video-analysis | ai | 동영상 키프레임 분석 |
| builtin-wd-tagger | ai | WD-Tagger 자동 태그 생성 |
| builtin-webhook | integration | Webhook 송수신 |

---

## 10. 설정（config.json）

**경로**: `{프로젝트 루트}/config.json`

```json
{
  "scan_roots": [
    {
      "path": "/path/to/images",
      "enabled": true,
      "recursive": true,
      "comment": "메인 이미지 폴더"
    }
  ],

  "server": {
    "host": "127.0.0.1",
    "port": 5000,
    "lan": false,
    "pin": null,
    "allow_remote_restart": false
  },

  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "local",
        "base_url": "http://localhost:11434",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "fast": "local/qwen2.5:7b",
      "large": "local/qwen2.5:32b"
    }
  },

  "api_keys": [
    {
      "id": "ak_...",
      "key_hash": "<sha256_hex>",
      "key_prefix": "sk_...",
      "label": "Claude Desktop",
      "scopes": ["read", "write", "admin"]
    }
  ],

  "ai_analysis": {
    "engine": "claude",
    "model": "claude-opus-4-7",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llava",
    "language": "ja"
  },

  "wd_tagger": {
    "model": "WD14",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "engine_type": "onnx"
  },

  "inference_servers": [
    {
      "id": "hailo-1",
      "name": "Hailo Server",
      "endpoint_url": "http://localhost:8080",
      "priority": 100,
      "enabled": true,
      "inference_types": ["clip", "yolo"],
      "timeout": 30
    }
  ],

  "extensions": {
    "builtin-analysis": {
      "enabled": true
    }
  },

  "mdns": {
    "bind_address": "0.0.0.0"
  }
}
```

### 환경 변수

| 변수 | 설명 |
|-----|------|
| `TAGDB_DATA_DIR` | 데이터 디렉토리 |
| `TAGDB_CACHE_DIR` | 캐시 디렉토리 |
| `TAGDB_LOG_DIR` | 로그 디렉토리 |
| `TAGDB_PROFILES_DIR` | 프로필 디렉토리 |
| `YU_DEBUG_MODE` | `1`로 디버그 API 활성화 |

---

## 11. 파일 구조

```
O:/yu_ai_manager/
├── web_ui.py              # ASGI 엔트리 포인트
├── app.py                 # Quart 앱 초기화
├── config.json            # 메인 설정
├── tags.db                # 개발용 DB（--db로 지정）
├── VERSION                # 버전 번호
├── CHANGELOG.md           # 변경 이력
├── TODO.md                # 이슈 관리
│
├── routes/                # REST API Blueprint
│   ├── agent_safety.py
│   ├── analysis.py
│   ├── collections.py
│   ├── debug.py
│   ├── favorites.py
│   ├── files.py
│   ├── maintenance.py
│   ├── ratings.py
│   ├── scan.py
│   ├── scan_roots.py
│   ├── server_info.py
│   ├── settings.py
│   └── tags.py
│
├── core/                  # 코어 모듈
│   ├── agent_safety/      # 안전 기구
│   ├── analysis/          # AI 분석 엔진
│   ├── event_bus/         # 이벤트 버스
│   ├── extensions_core/   # 확장 라이프사이클
│   ├── files_core/        # 파일 서브
│   ├── infra_core/        # API 응답 등
│   ├── llm_router/        # LLM 라우팅
│   ├── scan_core/         # 스캔
│   ├── schema_core/       # DB Schema·마이그레이션
│   ├── services_core/     # DB 비동기 어댑터
│   ├── settings_core/     # 설정 관리
│   ├── sse/               # SSE 브로드캐스터
│   ├── tagdb_core/        # 태그 DB 코어
│   └── web/               # 인증·요청 처리
│
├── mcp_server/            # MCP Server（180+ 도구）
│   ├── server.py          # FastMCP 엔트리
│   ├── tools/             # 도구 정의
│   └── interceptor.py     # Safety 인터셉터
│
├── extensions/            # 확장（47 builtin）
│   └── builtin-*/
│
├── src/ts/                # TypeScript 프론트엔드
│   ├── main/              # 메인 화면
│   ├── nav/               # 내비게이션
│   ├── tools-page/        # 도구 페이지
│   └── types/             # 타입 정의
│
├── src-tauri/             # Tauri 데스크톱
│
├── ui/default/            # HTML 템플릿
│   ├── templates/
│   └── static/dist/       # 빌드된 JS
│
├── docs/                  # 문서（ja/가 1차 소스）
│   ├── ja/                # 일본어（1차 소스）
│   │   ├── SPEC.md        # 본 파일
│   │   ├── features/
│   │   ├── api/
│   │   └── troubleshooting/
│   └── bugreport.html     # 버그 리포트 릴레이 페이지
│
└── scripts/
    ├── find_port.py       # 빈 포트 자동 취득
    └── ...
```

---

## 12. 개발 규약

### 버전 관리

- `feat:` → minor 버전 업
- `fix:` → patch 버전 업
- 작업마다 `VERSION` / `CHANGELOG.md` / `TODO.md` 갱신

### 코딩

- Blueprint 추가 시 i18n 필수（`data-i18n` / `window.tr()`）
- HTML 폼 요소에는 `id` 또는 `name` 부여
- `type="password"`는 `<form>`으로 감싸기
- 인라인 `onclick` 금지（`data-action` 위임 사용）
- DB 읽기/쓰기 분리: GET 계열은 반드시 `get_readonly_db()` 사용

### 파일 크기 제한

| 줄 수 | 대응 |
|-----|------|
| 300 | 분할 검토 |
| 500 | 실용 상한 |
| 800 | 즉시 분할 |

### 라이선스 금지

GPL / LGPL / AGPL 계열의 신규 의존 추가 금지.

### 문서

- 신규 API: MCP 도구 동시 구현 + `docs/{ja,en,zh-tw,zh-cn,ko}/api/`에 전체 언어 문서 작성
- 신규 기능: `docs/{ja,en,zh-tw,zh-cn,ko}/`에 전체 언어 작성（스텁 금지）
- 다국어 문서는 `ja/`가 1차 소스, 다른 언어는 ja/ 기반으로 생성

### 테스트

- WebUI/CSS 변경 후 Playwright 테스트 실시
- CSS는 라이트·다크 양 모드 확인
- 테스트 서버는 반드시 5100 이상의 포트 사용
- 임시 파일은 `tmp/` 아래에 배치하고 작업 완료 후 삭제

---

*본 문서는 `docs/ko/SPEC.md`에 저장되어 있습니다. 내용이 오래된 경우 코드와 git log를 참조하세요.*
