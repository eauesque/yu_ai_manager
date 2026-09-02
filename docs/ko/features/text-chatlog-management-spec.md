# YU AI Manager 텍스트 및 채팅 로그 관리 사양

작성: 2026-03-01
대상 버전: 미정 (구현 시기 검토 중)

## 개요

YU AI Manager에 세 가지 기능을 추가합니다:

- **MD 뷰어** — Markdown 파일의 로컬 열람
- **채팅 로그 관리** — Claude/ChatGPT/Open WebUI의 로그 가져오기, 열람, 검색
- **전문 검색** — FTS5 기반의 크로스 콘텐츠 검색

설계 철학은 기존 기능과 동일합니다: "완전 로컬, 클라우드 의존 없음."

---

## 1. MD 뷰어

### 목적

OS 파일 뷰어는 Markdown 렌더링 품질이 좋지 않습니다. 이 기능은 Markdown 열람을 YU AI Manager 내부에서 완결시켜, 개발 노트, 설계 문서, TODO 목록 등의 일상적인 참조 도구로 활용합니다.

### 스캔 대상

- 확장자: `.md`, `.markdown`
- 기존 스캔 루트를 재사용
- 제외: `.git/` 및 `node_modules/` 아래의 파일

### DB 스키마

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- 첫 번째 # 제목에서 추출
    content     TEXT,        -- 원시 Markdown 텍스트
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### 뷰어 UI

- 기존 모달 또는 사이드 패널에 통합
- 렌더링: marked.js (로컬 번들, CDN 미사용)
- 코드 블록: 구문 강조 (highlight.js)
- 원시 텍스트 보기 토글 버튼 제공

### MCP 지원

- `search_md_files(query, path_filter)` -> 파일 목록
- `get_md_content(file_id)` -> 원시 텍스트

---

## 2. 채팅 로그 관리

### 목적

이 기능은 개발 이력의 검색 엔진 역할을 하여, 모호한 키워드로 과거 논의를 찾을 수 있게 합니다. 예: "그 버그 논의가 어디였지?" 또는 "그 설계 결정의 이유가 뭐였지?"

### 지원 형식

| 서비스 | 내보내기 형식 | 취득 방법 |
|---|---|---|
| Claude | conversations.json | 설정 -> 데이터 내보내기 |
| ChatGPT | conversations.json | 설정 -> 데이터 내보내기 |
| Open WebUI | JSON 내보내기 | 채팅 기록 -> 내보내기 |

### DB 스키마

```sql
-- 대화 단위
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- 원본 서비스의 대화 ID
    title         TEXT,
    model         TEXT,           -- 사용된 모델명
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- 메시지 단위
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- 대화 내 순서
);

-- FTS5 전문 검색
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### 임포터

각 서비스의 JSON을 공통 중간 형식으로 변환하여 DB에 삽입합니다.

**Claude JSON 구조 (주요 필드):**

```json
{
  "uuid": "...",
  "name": "대화 제목",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**ChatGPT JSON 구조 (주요 필드):**

```json
{
  "id": "...",
  "title": "대화 제목",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Open WebUI JSON 구조:**

- OpenAI 호환 API 형식을 따름
- role/content가 포함된 messages 배열

### 가져오기 UI

- 설정 페이지에 가져오기 섹션 추가
- 드래그 앤 드롭 또는 파일 선택기를 통해 JSON 파일 선택
- 이전에 가져온 대화는 `external_id`로 중복 제거 (멱등)
- 가져오기 요약 (추가 수 및 건너뛴 수) 표시

### 뷰어 UI

- 대화 목록 페이지 (제목, 날짜, 모델, 소스)
- 대화 상세 페이지 (역할별 색상 구분의 턴 기반 표시)
- 모델명, 소스, 날짜 범위별 필터
- 첨부 이미지는 경로 참조만 저장 (파일 복사 없음)

### MCP 지원

- `search_chat_logs(query, source, model, date_from, date_to)` -> 대화 목록
- `get_conversation(conversation_id)` -> 메시지 목록
- `import_chat_log(source, json_path)` -> 가져오기 실행

---

## 3. 전문 검색

### 대상

- MD 파일 (`md_files_fts`)
- 채팅 로그 (`chat_messages_fts`)
- 기존 프롬프트 라이브러리 (`prompt_library_fts`, 이미 구현)

### 검색 UI

- 기존 검색바를 확장하거나 전용 텍스트 검색 페이지 제공
- 검색 대상 토글 (MD / 채팅 로그 / 프롬프트 라이브러리)
- BM25 점수순 결과 정렬
- 히트 스니펫 표시 (주변 ~50자 문맥)

### 검색 API

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

응답:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "대화 제목",
      "snippet": "...히트 주변 텍스트...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## 구현 우선순위

1. MD 뷰어 (구현 비용 낮음, 즉각적 가치 높음)
2. 채팅 로그 임포터 (Claude/ChatGPT 지원 우선)
3. 채팅 로그 뷰어
4. Open WebUI 지원
5. 크로스 콘텐츠 텍스트 검색 UI

---

## 향후 확장

- 채팅 로그 자동 정기 가져오기 (감시 폴더에 내보내기 파일을 배치하면 자동 수집)
- 이미지 생성 프롬프트와 이를 생성한 채팅 로그 논의를 연결
- Ollama를 통한 채팅 로그 자동 요약 및 태깅

---

## 참고 사항

- FTS5 패턴은 기존 `prompt_library_fts` 구현에서 재사용 가능
- marked.js는 CDN이 아닌 로컬 번들로 사용 (로컬 전용 설계 철학에 따름)
- 채팅 로그의 첨부 이미지 (DALL-E 생성 이미지 등)는 URL이 만료되므로 로컬에 저장하지 않음
