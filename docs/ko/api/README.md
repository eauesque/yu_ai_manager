# YU AI Manager API 레퍼런스

이 REST API 문서는 YU AI Manager의 모든 기능을 다루며, 커스텀 UI 및 스크립트에서 사용할 수 있습니다.

## 공통 규약

### Base URL

```
http://<host>:<port>
```

기본값: `http://127.0.0.1:5000`
테스트 환경: `http://127.0.0.1:5100` (`config_test.json` 사용 시)

### 인증

네 가지 인증 방식을 지원합니다:

| 방식 | 용도 | 헤더 예시 |
|--------|----------|----------------|
| PIN 인증 | 브라우저 세션 | Cookie: `session=...` |
| API Key | 머신 간 통신 | `Authorization: Bearer sk_...` |
| Trusted Proxy | 리버스 프록시 뒤에서 사용 | `X-Remote-User: username` |
| LAN Share Token | 게스트 접근 | URL 경로 `/s/<token>/...` |

`config_test.json`(PIN 없음)으로 실행하면 인증을 완전히 건너뛸 수 있습니다.

### CSRF 보호

`/api/` 엔드포인트에 대한 모든 `POST` / `PUT` / `DELETE` 요청에는 `X-Requested-With` 헤더가 필요합니다:

```
X-Requested-With: XMLHttpRequest
```

**예외**: `Authorization: Bearer` 헤더를 사용하는 API Key 요청은 CSRF가 필요하지 않습니다.

### 속도 제한

| 티어 | 범위 | 속도 | 버스트 |
|------|-------|------|-------|
| READ | 모든 GET | 무제한 | - |
| WRITE | POST/PUT/DELETE (일반) | ~120 req/min | 30 |
| HEAVY | 유사 검색, 해시 계산, AI 분석, 스캔 | ~20 req/min | 5 |
| DESTRUCTIVE | 퍼지, 완전 삭제, 캐시 클리어, 설정 쓰기 | ~12 req/min | 3 |

429 응답에는 `Retry-After` 헤더가 포함됩니다.

### 응답 형식

**성공** (신규 API):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**오류**:
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "detail": "Additional details (optional)"
}
```

일부 레거시 API는 `{ "success": true, "message": "..." }` 형식을 반환합니다.

### 페이지네이션

**오프셋 기반** (기본):
```
GET /api/search?offset=0&limit=50
```

**커서 기반** (대규모 데이터셋용):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

응답에 `next_cursor` 필드가 포함됩니다.

### 일괄 작업

일괄 API는 요청당 최대 500개의 작업을 지원합니다. 부분 성공이 가능합니다:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## API 카테고리

| 문서 | 내용 |
|----------|---------|
| [search.md](search.md) | 검색, 제안, 그룹 |
| [files.md](files.md) | 파일 상세정보, 썸네일, 미디어 조회 |
| [scan.md](scan.md) | 스캔 제어, 스캔 루트 관리 |
| [events.md](events.md) | SSE 이벤트 스트림 |
| [theming.md](theming.md) | CSS 변수, 테마 커스터마이징 |
| [source.md](source.md) | 소스 코드 브라우징 (MCP용 읽기 전용) |
| [github.md](github.md) | GitHub Integration (계정 관리・Issue・PR・알림・Discussion・Release) |
| [scheduler.md](scheduler.md) | 작업 스케줄러 (작업 관리・실행 이력) |
| [ratings.md](ratings.md) | 평점 (설정・일괄 설정・조회・통계) |
| [favorites.md](favorites.md) | 즐겨찾기 (토글・확인・목록) |
| [collections.md](collections.md) | 컬렉션 (CRUD・정렬・일괄 추가/제거・CSV 내보내기) |
| [tags.md](tags.md) | 태그 (일괄 설정・제안) |
| [sns.md](sns.md) | SNS 공유 & Bluesky 모니터 (게시・알림・트리아지・자동 응답) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (설정・단일/일괄 태그 부여・태그 CRUD) |
| [tagger-servers.md](tagger-servers.md) | Tagger Server Registry (분산 태그 추론 클러스터・서버 관리・배치 실행) |
| [svg.md](svg.md) | SVG 래스터화 (SVG → PNG/WebP 변환, img2img 파이프라인 지원) |
| [system-update.md](system-update.md) | 시스템 업데이트 (버전 확인・업데이트 적용・통합 업데이트 관리자) |
| [tools.md](tools.md) | 도구 (중복 감지・해시 계산・유사 검색・캐시 관리・백업・아카이브 정리・디버그 로그) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch・Circuit Breaker・Budget・Approval・Scope Fence・Undo・이상 감지) |
| [profiles.md](profiles.md) | 프로필 관리 (CRUD・복제・QR 내보내기/가져오기) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (Danbooru 자동 태깅・모델 관리・VLM・XMP) |
| [ocr.md](ocr.md) | OCR (문자 인식・번역・동영상/PDF 지원・벤치마크・프로필) |
| [apikeys.md](apikeys.md) | API Key 관리 (생성・목록・스코프・폐기) |
| [debug.md](debug.md) | 디버그 (메타데이터 검사・SQL 쿼리・모델 검증) |
| [ui.md](ui.md) | UI 관리 (목록・전환・설치・삭제) |
| [video-analysis.md](video-analysis.md) | 동영상 분석 (설정・상태・키프레임 추출) |
| [extensions.md](extensions.md) | Extension 관리 (목록・활성화・설정・설치・보안・마켓플레이스・저작) |
| [settings.md](settings.md) | 설정 관리 (스키마・값 가져오기/업데이트・시크릿 암호화・1Password/Bitwarden 연동) |
| [analysis.md](analysis.md) | AI 분석 (설정・단일/배치 분석・트렌드 분석・통계・서버 레지스트리) |

## 빠른 시작 (curl)

```bash
# 검색 (PIN 없는 환경)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# 썸네일 조회
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# API Key를 사용한 검색
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# 평점 설정
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
