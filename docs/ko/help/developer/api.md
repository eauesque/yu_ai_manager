# API 개요

YU AI Manager는 WebUI의 모든 작업을 프로그래밍 방식으로 수행할 수 있는 REST API를 제공합니다.
320개 이상의 엔드포인트로 이미지 관리부터 AI 분석까지 폭넓은 작업을 지원합니다.

> **팁**: 인증, CSRF, 속도 제한, 응답 형식 등 상세한 공통 규칙은 "API Reference" 섹션을 참조하세요.

## 인증

4가지 인증 방법을 지원합니다.

| 방법 | 용도 | 헤더/파라미터 |
|------|------|---------------|
| PIN 인증 | 브라우저 세션 | `/_pin`에서 로그인 -> 세션 쿠키 |
| API Key | 기계 간 통신 / MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | 리버스 프록시 | `X-Remote-User` 헤더 |
| LAN Share 토큰 | 게스트 접근 | `/s/<token>` 경로 |

### curl로 테스트

```bash
# API Key 인증 (CSRF 헤더 불요)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN 인증은 2단계 필요
# 1. CSRF 토큰 획득
curl -c cookies.txt http://localhost:5000/_pin
# 2. PIN 제출
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF 보호

모든 POST/PUT/DELETE `/api/` 엔드포인트에 `X-Requested-With` 헤더가 필요합니다.
Bearer API Key 요청에는 불요합니다.

## 주요 엔드포인트

### 이미지 검색 및 보기

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/search` | 태그, 날짜, 평가 등으로 필터 검색 |
| GET | `/api/search-grouped` | 폴더/ZIP별 그룹 검색 |
| GET | `/api/file/<id>` | 상세 이미지 메타데이터 조회 |
| GET | `/api/thumbnail/<id>` | 썸네일 조회 (WebP, ETag 캐싱) |
| GET | `/api/original/<id>` | 원본 이미지 조회 (Range 요청 지원) |
| GET | `/api/suggest` | 태그 자동완성 제안 |

### 평가, 태그, 어노테이션

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/ratings/batch-set` | 배치 평가 설정 |
| POST | `/api/tags/batch-set` | 배치 태그 편집 |
| POST | `/api/annotations/batch-set` | 배치 어노테이션 설정 |
| GET | `/api/annotations/<id>` | 어노테이션 조회 |
| GET | `/api/annotations/search` | 어노테이션 검색 |

### 컬렉션

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/collections` | 컬렉션 목록 |
| POST | `/api/collections` | 컬렉션 생성 |
| PUT | `/api/collections/<id>` | 컬렉션 이름 변경 |
| DELETE | `/api/collections/<id>` | 컬렉션 삭제 |
| POST | `/api/collections/<id>/batch-add` | 배치 파일 추가 |
| POST | `/api/collections/<id>/batch-remove` | 배치 파일 제거 |

### 스캔

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/scan/start` | 스캔 시작 |
| GET | `/api/scan/status` | 스캔 진행률 조회 |
| POST | `/api/scan/cancel` | 스캔 취소 |
| POST | `/api/scan/resume` | 중단된 스캔 재개 |
| GET | `/api/scan-roots` | 스캔 루트 목록 |
| POST | `/api/scan-roots` | 스캔 루트 추가 |

### AI 분석

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/analysis/analyze/<id>` | AI 이미지 분석 실행 |
| GET | `/api/analysis/result/<id>` | 분석 결과 조회 |
| POST | `/api/analysis/batch` | 배치 분석 |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger 추론 |
| POST | `/api/wd-tagger/batch` | WD-Tagger 배치 추론 |
| POST | `/api/analysis/batch/cancel` | AI 분석 배치 취소 |
| POST | `/api/wd-tagger/batch/cancel` | WD-Tagger 배치 취소 |
| POST | `/api/tagger-servers/batch/cancel` | 태거 클러스터 배치 취소 |
| POST | `/api/ocr/<id>` | OCR 실행 |

### 설정

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/settings/schema` | 설정 스키마 조회 |
| GET | `/api/settings/all` | 전체 설정 조회 |
| GET | `/api/settings/<key>` | 설정 값 조회 |
| PUT | `/api/settings/<key>` | 설정 값 업데이트 |

### Extension 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/extensions` | Extension 목록 |
| POST | `/api/extensions/<name>/toggle` | 활성화/비활성화 전환 |
| POST | `/api/extensions/install` | Git 리포지토리에서 설치 |
| DELETE | `/api/extensions/<name>/uninstall` | 제거 |

### Agent Safety

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/agent/kill` | Kill Switch 활성화 |
| POST | `/api/agent/resume` | Kill Switch 해제 |
| GET | `/api/agent/status` | 안전 메커니즘 상태 |
| GET | `/api/agent/journal` | 작업 저널 |
| POST | `/api/agent/undo/<journal_id>` | 작업 실행 취소 |

## 응답 형식

모든 API는 통일된 JSON 형식으로 응답합니다.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

오류 시:

```json
{
  "ok": false,
  "data": null,
  "error": "Error message"
}
```

## 속도 제한

3단계 토큰 버킷 시스템을 사용합니다.

| 단계 | 대상 | 제한 | 버스트 |
|------|------|------|--------|
| READ | 모든 GET 요청 | 무제한 | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | 유사 검색, AI 분석, 스캔 | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, 설정 쓰기 | ~12 req/min | 3 |

초과 시 HTTP 429가 반환됩니다. `Retry-After` 헤더에서 재시도 대기 시간(초)을 확인하세요.

## SSE (Server-Sent Events)

실시간 이벤트는 `/api/events/stream`의 SSE를 통해 전달됩니다.
자세한 내용은 "SSE Events" 섹션을 참조하세요.

> **참고**: IP당 최대 10개 동시 연결. 업로드 크기 제한은 100 MB입니다.

## 내부 설계 문서

API의 상세한 설계 근거, SQLite 성능 최적화, DB 스키마 설계, 기타 개발 인사이트는 [MD Viewer](/ext/md-viewer/)에서 확인할 수 있습니다.
