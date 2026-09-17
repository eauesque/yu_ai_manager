# LAN MCP 접근 및 도움말 엔드포인트 사양

**구현 버전**: 3.1.0
**관련 문서**: `docs/ko/features/mcp-integration-guide.md`
**관련 파일**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## 개요

1. **LAN MCP 접근** — LAN 공유 모드 활성화 시 LAN상의 MCP 클라이언트가 IP 주소로 MCP 엔드포인트에 연결할 수 있도록 합니다
2. **`/help` 엔드포인트** — 애플리케이션의 내장 웹 매뉴얼을 제공합니다 (MCP 리소스로도 공개)

---

## 1. LAN MCP 접근

### 1-1. 아키텍처

LAN을 통해 MCP 클라이언트가 HTTP/SSE 전송을 사용하여 YU AI Manager `/mcp` 엔드포인트에 직접 연결합니다.

### 1-2. MCP SSE 엔드포인트

| 항목 | 상세 |
|------|------|
| 엔드포인트 | `/mcp` (SSE + 메시지 포스팅) |
| 전송 | HTTP + Server-Sent Events (SSE) |
| 인증 | localhost에서는 불필요. LAN IP에서는 API 키 필요 |

### 1-3. API 키 인증

기존 API 키 관리 메커니즘 (`/api/keys`)을 재사용합니다.

### 1-4. 설정 UI

설정 > API Keys 탭에 LAN MCP 연결 설정 스니펫(HTTP 버전)을 추가합니다.

---

## 2. `/help` 엔드포인트

### 2-1. 설계 원칙

- 완전 오프라인
- MCP 리소스 겸용
- 인증 불필요

### 2-2. 엔드포인트

| 엔드포인트 | 내용 |
|----------------|------|
| `GET /help` | 매뉴얼 최상위 페이지 |
| `GET /help/<section>` | 섹션별 페이지 |
| `GET /api/help/toc` | 목차 JSON |
| `GET /api/help/content/<section>` | 섹션 본문 JSON |

### 2-3. MCP 도구

- `help_search`: 키워드 검색
- `help_get_section`: 섹션 조회
