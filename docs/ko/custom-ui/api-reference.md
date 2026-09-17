# API 레퍼런스 -- 커스텀 UI 개발자를 위한 링크 및 빠른 참조

이 페이지는 API 문서 링크와 자주 사용하는 API의 빠른 참조 표를 정리합니다.

## 문서 인덱스

### 공통 규칙

- [API 공통 규칙](../api/README.md) -- 기본 URL, 인증(4가지 방법), CSRF 보호, 속도 제한, 응답 형식, 페이지네이션

### 엔드포인트별

- [Search API](../api/search.md) -- GET /api/search, 제안, 그룹, server-info
- [Files API](../api/files.md) -- 파일 상세, 썸네일, 원본, 프롬프트 변환
- [Scan API](../api/scan.md) -- 스캔 제어, 스캔 루트 관리, 해시 백필
- [Events API](../api/events.md) -- SSE 실시간 이벤트, 로그 스트림

### 테마

- [CSS 변수 목록](../api/theming.md) -- 테마 커스텀 프로퍼티 (라이트/다크)

## 빠른 참조

### 읽기 작업 (GET, 인증 불요*)

| 엔드포인트 | 용도 | 주요 파라미터 |
|------------|------|---------------|
| `/api/search` | 파일 검색 | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | 썸네일 이미지 (WebP) | `size` (기본값 300) |
| `/api/original/<id>` | 원본 파일 | Range 지원 |
| `/api/file/<id>` | 파일 상세 | -- |
| `/api/suggest` | 태그 제안 | `q`, `limit` |
| `/api/stats/all` | 통계 | -- |
| `/api/collections` | 컬렉션 목록 | -- |
| `/api/server-info` | 서버 정보 | -- |
| `/api/events/stream` | SSE 스트림 | `types` |

*PIN 없는 환경 또는 인증된 세션에서 적용

### 쓰기 작업 (POST, `X-Requested-With` 헤더 필요)

| 엔드포인트 | 용도 | Body 예시 |
|------------|------|-----------|
| `/api/ratings/set` | 평가 설정 | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | 배치 평가 | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | 즐겨찾기 추가 | `{file_id: 42}` |
| `/api/favorites/remove` | 즐겨찾기 제거 | `{file_id: 42}` |
| `/api/tags/batch-set` | 배치 태그 작업 | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | 컬렉션 생성 | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | 컬렉션에 추가 | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | 스캔 시작 | `{}` |
| `/api/convert` | 프롬프트 변환 | `{prompt, direction}` |

### UI 관리

| 엔드포인트 | 메서드 | 용도 |
|------------|--------|------|
| `/api/ui/list` | GET | UI 목록 |
| `/api/ui/switch` | POST | UI 전환 |
| `/api/ui/install` | POST | UI 설치 (localhost만 가능) |
| `/api/ui/<name>/uninstall` | DELETE | UI 제거 (localhost만 가능) |

## 응답 형식

### 검색 결과

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = 미평가)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = 마지막 페이지
}
```

### 썸네일

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

브라우저가 썸네일을 자동으로 캐시합니다. `<img>` 태그에서 직접 참조할 수 있습니다:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### 오류 응답

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // 선택사항
  detail: "Retry after 5s"  // 선택사항
}
```

## CSRF 헤더 참고사항

```javascript
// 공통 헤더 헬퍼
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: 헤더 불요
fetch('/api/search?q=test');

// POST: X-Requested-With 필요
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```
