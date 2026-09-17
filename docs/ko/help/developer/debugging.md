# 디버깅 매뉴얼

YU AI Manager 디버깅을 위한 종합 가이드입니다.
개발자와 AI 에이전트가 효율적으로 버그를 조사하고 수정할 수 있도록 작성되었습니다.

---

## 목차

1. [서버 시작](#서버-시작)
2. [디버그 로깅](#디버그-로깅)
3. [테스트 실행](#테스트-실행)
4. [DB 디버깅](#db-디버깅)
5. [인증 우회 및 테스트](#인증-우회-및-테스트)
6. [MCP 디버깅](#mcp-디버깅)
7. [프론트엔드 디버깅](#프론트엔드-디버깅)
8. [환경 변수](#환경-변수)
9. [일반적인 오류와 해결책](#일반적인-오류와-해결책)
10. [성능 디버깅](#성능-디버깅)

---

## 서버 시작

### 개발 모드 (권장)

로컬 디버깅을 위해 PIN 인증 없이 시작합니다:

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

`config_test.json`이 없으면 다음 내용으로 생성하세요:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### 프로덕션 유사 (LAN 노출)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **참고**: `0.0.0.0`에 바인딩할 때 PIN이 필요합니다. v4.8.1부터 LAN 노출 시 `--debug` 플래그가 무시됩니다 (스택 트레이스 유출 방지).

### 포트 선택

5100 -> 5200 -> 5300 -> 100씩 증가. 시작 전 확인:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### CLI 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--db` | path | `data/tags.db` | SQLite DB 파일 경로 |
| `--config` | path | `config.json` | 설정 파일 경로 |
| `--host` | str | `127.0.0.1` | 바인드 주소 |
| `--port` | int | 5000 | 바인드 포트 |
| `--lan` | flag | - | `0.0.0.0`에 바인드 (LAN 접근) |
| `--pin` | str | - | PIN 인증 활성화 |
| `--debug` | flag | - | Quart 디버그 모드 활성화 |
| `--debug-log` | `on`/`off` | - | 구조화 디버그 로깅 활성화/비활성화 |
| `--debug-log-file` | path | `logs/debug.log` | 로그 파일 출력 경로 |
| `--debug-log-max-mb` | int | 10 | 로그 로테이션 크기 (MB) |
| `--debug-log-backups` | int | 5 | 로그 백업 세대 수 |
| `--debug-log-stdout` | `on`/`off` | `on` | stderr에도 출력 |
| `--allow-restart` | flag | - | `/api/server/restart` 활성화 |
| `--trusted-proxy-auth` | flag | - | Trusted Proxy 인증 활성화 |
| `--profile` | str | - | 시작 프로필 이름 |

### launch-args.txt

프로젝트 루트에 `launch-args.txt`를 배치하면 시작 시 인수가 자동 로드됩니다. CLI 인수가 우선합니다.

---

## 디버그 로깅

### 활성화

```bash
# CLI를 통해
python web_ui.py --db ./tags.db --debug-log on

# 환경 변수를 통해
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### 로그 형식

`dlog()` 함수 (`core/infra_core/debug_log.py`)를 통한 구조화 디버그 로그:

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

형식: `[DEBUG] timestamp | source | event_name | key=value, ...`

### 실시간 모니터링

```bash
# 로그 파일 tail
tail -f logs/debug.log

# API를 통해
curl http://127.0.0.1:5100/api/debug/logs

# SSE 스트리밍
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### 로그 링 버퍼

실행 중인 로그는 인메모리 링 버퍼에도 저장됩니다 (최대 1000개 항목). 서버 재시작 시 손실되므로 영속적인 기록에는 파일 로깅을 사용하세요.

---

## 테스트 실행

### 단위 테스트

```bash
source venv/Scripts/activate

# 모든 테스트 실행
python -m pytest tests/test_basic.py -v

# 특정 테스트만
python -m pytest tests/test_basic.py::TestImports -v

# 첫 실패에서 중지
python -m pytest tests/test_basic.py -x
```

### API 통합 테스트

```bash
python -m pytest tests/api/ -v
```

### Playwright 브라우저 테스트

```bash
# 1. 테스트 서버 시작
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. 테스트 실행
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### 테스트 출력

- 스크린샷: `screenshots/`
- 보고서: `reports/`

---

## DB 디버깅

### 스키마 버전 확인

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### 상태 검사

```bash
python db_health.py --db ./tags.db
```

### 디버그 SQL 실행

`YU_DEBUG_MODE=1`일 때만 사용 가능:

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **참고**: v4.8.1부터 SELECT 문만 허용됩니다.

### 유용한 조사 쿼리

```sql
-- 소스별 파일 수
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- 모델 사용 순위
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- 고아 태그
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- 중복 경로 감지
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### DB 연결 규칙

| 함수 | 용도 | 사용 시점 |
|------|------|-----------|
| `get_readonly_db()` | 읽기 전용 | GET API, 검색, 썸네일, 통계 |
| `get_db()` | 읽기-쓰기 (Row factory) | POST/PUT/DELETE API |
| `get_raw_db()` | 읽기-쓰기 (Row factory 없음) | 배치 처리, 스캔, 마이그레이션 |

> **중요**: 읽기 전용 API에서 `get_db()`를 사용하면 스캔 중 쓰기 잠금 경합이 발생하여 뷰어가 수 초간 블로킹됩니다. 반드시 `get_readonly_db()`를 사용하세요.

---

## 인증 우회 및 테스트

### PIN 인증 건너뛰기

`config_test.json` (PIN 미설정)으로 시작하면 모든 인증을 건너뜁니다.

### API Key 테스트

```bash
# Bearer 토큰 요청 (CSRF 헤더 불요)
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API Key 스코프

v4.8.1부터 스코프 없는 키는 기본적으로 **읽기 전용**입니다.

| 스코프 | 허용 작업 |
|--------|-----------|
| `read` | 검색, 파일 상세, 썸네일, 통계 |
| `rate` | 평가 설정/조회/배치 |
| `tag.write` | 태그 추가/제거 |
| `collection.write` | 컬렉션 CRUD, 즐겨찾기 |
| `annotate` | 어노테이션 읽기/쓰기 |
| `scan` | 스캔 시작/취소/재개 |
| `admin` | API 키 관리, 설정, 백업/복원 |

### 인증 체인 순서

```
static -> /s/ (LAN Share) -> /_pin -> API Key Bearer
-> QuickLock -> Trusted Proxy -> session -> cookie -> PIN 페이지
```

---

## MCP 디버깅

### MCP 서버 시작

```bash
source venv/Scripts/activate
python -m mcp_server
```

### 디버그 도구 활성화

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### 디버그 도구 (9개, YU_DEBUG_MODE=1)

| 도구 | 용도 |
|------|------|
| `debug_health_check` | 서버, DB, 테이블 상태 검사 |
| `debug_validate_counts` | API 통계 vs DB 실제 수 비교 |
| `debug_validate_search` | 검색 API 회귀 테스트 |
| `debug_validate_collection` | 컬렉션 수 일관성 |
| `debug_validate_annotations` | 어노테이션 테이블 무결성 |
| `debug_sample_files` | 랜덤 샘플링 필드 분석 |
| `debug_roundtrip_test` | 어노테이션/평가/태그 왕복 테스트 |
| `debug_readonly_query` | 임의 SELECT 쿼리 실행 |
| `debug_full_report` | 도구 1-5의 결합 보고서 |

### Import 확인

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Extension 보안 스캔

YU AI Manager에는 Extension용 내장 코드 스캔 기능이 있습니다. 스캔은 **Extension 로드 시 자동으로 실행**되므로, Extension을 추가하거나 수정한 후 서버를 재시작하여 스캔을 트리거하세요.

### 자동 스캔 동작

Extension 로드 시 다음 검사가 순차적으로 실행됩니다:

```
1. ManifestAuthority.review()   -- 매니페스트 검토 (형식, 권한 유효성)
2. CodeVerifier.verify()        -- AST 정적 분석 (모든 .py 파일 코드 스캔)
3. 사용자 동의 확인             -- 권한 승인/거부
4. Capability Token 발급        -- 실행 권한 토큰
```

### CodeVerifier가 감지하는 항목

| 카테고리 | 대상 | 심각도 |
|----------|------|--------|
| 위험한 모듈 | `subprocess`, `ctypes`, `importlib` | block |
| 직접 DB 접근 | `import sqlite3` (SandboxedDB 사용 필요) | block |
| 네트워크 | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| 동적 코드 실행 | `eval()`, `exec()`, `__import__()`, `compile()` | block |

`block` 심각도 발견 시 Extension 로딩이 거부됩니다.

### 스캔 실행 방법

**일반 흐름 (권장):**

Extension을 추가하거나 수정한 후 서버를 재시작하세요. 로딩 중 스캔이 자동으로 실행되며, 결과가 로그에 출력됩니다.

```bash
# Extension 재로드를 위해 서버 재시작 (스캔 자동 실행)
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**수동 스캔만:**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# 결과 확인
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### 신뢰 수준

| 수준 | 조건 | 제한 |
|------|------|------|
| L0 Trusted | `builtin-` 접두사 | 제한 없음 |
| L1 Verified | 서명 검증됨 | 선언된 권한만 |
| L2 Untrusted | 수동 설치 | 선언된 권한 + 사용자 동의 필요 |

### 런타임 보호

로딩 후에도 보호가 계속됩니다:

- **Import Guard**: `sys.meta_path`를 통한 비인가 모듈 import 차단
- **Integrity Monitor**: 5분마다 SHA-256 해시를 비교하여 파일 변조 감지
- **토큰 자동 취소**: 위반 감지 시 Capability Token을 취소하여 실행 중지

### 관련 문서

| 문서 | 위치 |
|------|------|
| 삼권분립 보안 모델 | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| 샌드박스 사양 | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| 훅 사양 | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## 프론트엔드 디버깅

### TypeScript 빌드

```bash
pnpm run build        # esbuild 번들
pnpm run typecheck    # tsc --noEmit (타입 검사만)
```

출력: `ui/default/static/dist/` (gitignored)

### CSRF 인터셉터

`src/ts/nav/csrf-fetch.ts`가 글로벌 `fetch`를 Proxy로 래핑하여 모든 POST/PUT/DELETE 요청에 `X-Requested-With` 헤더를 자동 주입합니다.

### SSE 공유 엔진

`window.EventSource`가 Proxy로 덮어쓰여 있습니다. 직접 `new EventSource()`를 사용하면 오류가 발생합니다.

```javascript
// 올바른 방법
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// 잘못된 방법 (런타임 오류)
// new EventSource('/api/events/...')
```

### i18n 디버깅

```javascript
window.setLang('en');
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## 환경 변수

### 디버그 / 로깅

| 변수 | 값 | 기본값 | 설명 |
|------|-----|--------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | 구조화 디버그 로깅 활성화 |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | 로그 파일 경로 |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | 로그 로테이션 크기 (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | 백업 세대 수 |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | stderr에 출력 |

### 서버

| 변수 | 값 | 설명 |
|------|-----|------|
| `TAGDB_DB` | path | DB 파일 경로 |
| `TAGDB_CONFIG` | path | config.json 경로 |
| `TAGDB_PROFILE` | str | 시작 프로필 이름 |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | 재시작 API 활성화 |

### MCP

| 변수 | 값 | 설명 |
|------|-----|------|
| `YU_DEBUG_MODE` | `1` | 9개 디버그 도구 등록 |
| `YU_BASE_URL` | URL | MCP 클라이언트 기본 URL |
| `YU_API_KEY` | `sk_...` | MCP 클라이언트 API 키 |

---

## 일반적인 오류와 해결책

### 서버 시작

| 오류 | 원인 | 수정 |
|------|------|------|
| `Address already in use` | 포트 사용 중 | `--port 5200` 사용 |
| `database is locked` | DB 잠금 경합 | DB가 로컬 디스크에 있는지 확인 |
| `--pin is required` | PIN 없이 LAN 바인드 | `--pin <digit>` 추가 |
| `ModuleNotFoundError` | venv 미활성화 | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### 인증

| 오류 | 원인 | 수정 |
|------|------|------|
| PIN 페이지 반복 | 쿠키 문제 | DevTools에서 쿠키 확인 |
| `CSRF header missing` (403) | `X-Requested-With` 누락 | fetch 요청에 헤더 추가 |
| API Key 거부 | 스코프 부족 | 필요한 스코프 할당 (v4.8.1+) |

### Windows 전용

| 오류 | 원인 | 수정 |
|------|------|------|
| print의 `UnicodeEncodeError` | cp932 인코딩 | ASCII 안전 문자 사용 |
| `pkill` 동작 안 함 | Git Bash 제한 | `taskkill //F //PID <pid>` 사용 |

---

## 성능 디버깅

### 스캔 중 뷰어 블로킹

**증상**: 스캔 중 이미지 로딩이 5-10초간 중지

**원인**: 읽기 전용 API가 `get_db()` (쓰기 가능 연결)을 사용

**수정**: 모든 읽기 전용 API에 `get_readonly_db()` 사용

### 속도 제한

| 단계 | 대상 | 제한 |
|------|------|------|
| **HEAVY** | 유사 검색, 해시, AI 분석, 스캔 | ~20 req/min (버스트 5) |
| **DESTRUCTIVE** | purge, hard-delete, 캐시 삭제 | ~12 req/min (버스트 3) |
| **WRITE** | 기타 POST/PUT/DELETE | ~120 req/min (버스트 30) |
| GET | 읽기 | 무제한 |

429 응답 시 `Retry-After` 헤더를 확인하세요.

---

## 관련 문서

| 문서 | 위치 |
|------|------|
| DB 읽기/쓰기 분리 | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| 오류 형식 표준 | `docs/development/development_docs/ERROR_HANDLING.md` |
| 크로스 플랫폼 이슈 | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP 디버그 도구 사양 | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Quart 마이그레이션 로그 | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| QA 인수인계 | `docs/development/development_docs/QA_HANDOFF.md` |
| 보안 체크리스트 | `/security-check` 스킬 |
