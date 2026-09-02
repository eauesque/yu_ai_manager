# 고급 가이드 -- SSE, 배치 작업, 보안

이 가이드는 커스텀 UI의 고급 기능과 구현 패턴을 다룹니다.

## 실시간 업데이트 (SSE)

Server-Sent Events를 사용하면 스캔 진행률, 즐겨찾기 변경, AI 분석 진행 상황 등의 실시간 알림을 UI에서 수신할 수 있습니다.

### 연결

```javascript
// EventSource를 직접 사용합니다 (커스텀 UI에서는 안전합니다)
const sse = new EventSource('/api/events/stream');

// 이벤트 구독
sse.addEventListener('scan.progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`스캔: ${data.scanned}/${data.total}`);
});

sse.addEventListener('scan.complete', (e) => {
  const data = JSON.parse(e.data);
  console.log(`스캔 완료: ${data.added_count}개 추가`);
  // 그리드 다시 로드
  reloadResults();
});
```

**참고**: 레퍼런스 UI(`ui/default/`)는 `window.EventSource`를 Proxy로 덮어쓰기 때문에 `new EventSource()`가 동작하지 않습니다. 이 제한은 커스텀 UI에는 적용되지 않으며, EventSource를 직접 사용할 수 있습니다.

### 주요 이벤트

| 이벤트 | 데이터 | UI 용도 |
|--------|--------|---------|
| `scan.progress` | `{ scanned, total, current_file }` | 진행률 바 |
| `scan.complete` | `{ added_count, updated_count }` | 검색 결과 다시 로드 |
| `favorite.add` | `{ file_id, collection_id }` | 즐겨찾기 아이콘 업데이트 |
| `favorite.remove` | `{ file_id, collection_id }` | 즐겨찾기 아이콘 업데이트 |
| `collection.create` | `{ id, name }` | 컬렉션 목록 업데이트 |

모든 이벤트 유형은 [events.md](../api/events.md)를 참조하세요.

### 연결 관리

```javascript
class SSEConnection {
  constructor() {
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    this.sse = new EventSource('/api/events/stream');
    this.sse.onerror = () => {
      this.sse.close();
      // 지수 백오프로 재연결
      setTimeout(() => this.connect(), 3000);
    };
    // 기존 핸들러 재등록
    for (const [type, handler] of this.handlers) {
      this.sse.addEventListener(type, handler);
    }
  }

  on(eventType, callback) {
    const handler = (e) => callback(JSON.parse(e.data));
    this.handlers.set(eventType, handler);
    this.sse.addEventListener(eventType, handler);
  }

  close() {
    this.sse.close();
  }
}

// 사용 예
const sse = new SSEConnection();
sse.on('scan.progress', (data) => updateProgressBar(data));
sse.on('scan.complete', () => reloadResults());
```

### 가시성 인식 연결

탭이 숨겨지면 연결을 닫고 다시 보이면 재연결하여 리소스를 절약할 수 있습니다:

```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    sse.close();
  } else {
    sse.connect();
  }
});
```

## 배치 작업

여러 파일에 대해 한 번에 작업을 수행하는 API 패턴입니다.

### 배치 평가

```javascript
async function batchRate(items) {
  // items: [{file_id: 1, rating: 5}, {file_id: 2, rating: 3}]
  // 최대 500개
  const res = await api('/api/ratings/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### 배치 태그 작업

```javascript
async function batchSetTags(items) {
  // items: [{file_id: 1, add: ["good"], remove: ["bad"]}, ...]
  const res = await api('/api/tags/batch-set', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
  return res;
}
```

### 배치 컬렉션 작업

```javascript
// 컬렉션에 추가
async function addToCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-add`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}

// 컬렉션에서 제거
async function removeFromCollection(collectionId, fileIds) {
  return api(`/api/collections/${collectionId}/batch-remove`, {
    method: 'POST',
    body: JSON.stringify({ file_ids: fileIds }),
  });
}
```

### 부분 실패 처리

배치 작업은 부분적으로 성공할 수 있습니다:

```javascript
const result = await batchRate(items);
if (result.failed && result.failed.length > 0) {
  console.warn(`${result.failed.length}개 항목 실패:`, result.failed);
  showToast(`${result.succeeded}개 성공, ${result.failed.length}개 실패`);
}
```

## 오류 처리

### HTTP 상태 코드

| 코드 | 의미 | 조치 |
|------|------|------|
| 200 | 성공 | -- |
| 304 | 변경 없음 | 캐시 사용 (썸네일) |
| 400 | 잘못된 요청 | 입력 확인 |
| 403 | 인증 실패 / 잘못된 CSRF | `X-Requested-With` 헤더 확인 |
| 404 | 리소스를 찾을 수 없음 | 파일 ID 확인 |
| 429 | 속도 제한 | `Retry-After` 헤더의 초 수만큼 대기 |
| 500 | 서버 오류 | 재시도하거나 로그 확인 |

### 속도 제한 처리

```javascript
async function apiWithRetry(path, options = {}, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      },
    });

    if (res.status === 429) {
      const retryAfter = parseInt(res.headers.get('Retry-After') || '5', 10);
      console.warn(`속도 제한, ${retryAfter}초 후 재시도`);
      await new Promise(r => setTimeout(r, retryAfter * 1000));
      continue;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }

    return res.json();
  }
  throw new Error('Max retries exceeded');
}
```

### 응답 형식 감지

두 가지 응답 형식이 있습니다 (레거시 및 현재):

```javascript
function parseApiResponse(json) {
  // 현재 형식: { ok, error, data }
  if ('ok' in json) {
    if (!json.ok) throw new Error(json.error || 'Unknown error');
    return json.data ?? json;
  }
  // 레거시 형식: { success, message }
  if ('success' in json) {
    if (!json.success) throw new Error(json.message || 'Unknown error');
    return json;
  }
  // 직접 데이터 형식 (results 등)
  return json;
}
```

## 보안

### CSRF 보호

모든 쓰기 작업(POST / PUT / DELETE)에는 `X-Requested-With` 헤더가 필요합니다:

```javascript
// 올바른 예: 헤더 포함
fetch('/api/ratings/set', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

**예외**: `Authorization: Bearer sk_...` 헤더가 있는 API Key 요청은 CSRF 헤더가 필요하지 않습니다.

### XSS 방지

사용자 입력과 파일명을 DOM에 삽입하기 전에 새니타이즈하세요:

```javascript
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// 나쁜 예: 파일명을 직접 삽입
card.innerHTML = `<p>${file.filename}</p>`;  // XSS 위험

// 더 나은 방법: 먼저 이스케이프
card.innerHTML = `<p>${escapeHtml(file.filename)}</p>`;

// 가장 좋은 방법: DOM API 사용
const p = document.createElement('p');
p.textContent = file.filename;  // 자동 이스케이프
card.appendChild(p);
```

### API Key 처리

커스텀 UI를 구축할 때 클라이언트 사이드 코드에 API Key를 임베드하지 마세요. 브라우저 기반 UI는 CSRF 헤더로 보호되는 PIN / 세션 인증을 사용해야 합니다.

## 검색 구현

### 기본 검색

```javascript
async function search(query, options = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(options.limit || 50),
    sort: options.sort || 'date',
  });

  if (options.cursor) params.set('cursor', options.cursor);
  if (options.minRating) params.set('rating_min', String(options.minRating));
  if (options.collection) params.set('collection_id', String(options.collection));
  if (options.favOnly) params.set('favorites_only', 'true');

  const res = await fetch(`/api/search?${params}`);
  return res.json();
}
```

### 자동 완성

```javascript
let debounceTimer;

function onSearchInput(e) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const q = e.target.value;
    if (q.length < 2) return;

    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}&limit=10`);
    const { suggestions } = await res.json();
    showSuggestions(suggestions);  // [{value: "1girl", count: 5432}, ...]
  }, 200);
}
```

### 정렬 옵션

```javascript
const SORT_OPTIONS = [
  { value: 'date', label: 'Date (New)' },
  { value: 'name', label: 'Name' },
  { value: 'size', label: 'Size' },
  { value: 'rating', label: 'Rating' },
  { value: 'random', label: 'Random' },
];
```

## 컬렉션 관리

```javascript
// 컬렉션 목록
async function getCollections() {
  const res = await fetch('/api/collections');
  return res.json();
}

// 컬렉션 생성
async function createCollection(name) {
  return api('/api/collections', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

// 컬렉션 내 검색
async function searchInCollection(collectionId, query = '') {
  return search(query, { collection: collectionId });
}
```

## 프롬프트 변환

A1111과 NAI 형식 간 프롬프트를 변환합니다:

```javascript
async function convertPrompt(prompt, direction) {
  // direction: "a1111_to_nai" 또는 "nai_to_a1111"
  const res = await api('/api/convert', {
    method: 'POST',
    body: JSON.stringify({ prompt, direction }),
  });
  return res.converted;
}
```

## 배포

### 커스텀 UI 배포

커스텀 UI를 다른 사용자에게 배포하는 방법은 여러 가지가 있습니다:

1. **Git 리포지토리**: GitHub에 푸시한 후 설정 UI에서 설치
2. **ZIP 아카이브**: 파일을 ZIP으로 패키징하고 다운로드 URL 공유
3. **수동 배치**: `ui/<name>/` 디렉토리에 직접 복사

### 설치

설정 페이지의 "UI" 탭이나 API를 통해 설치합니다:

```bash
# curl로 설치
curl -X POST http://localhost:5000/api/ui/install \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-custom-ui.git"}'
```

### manifest.json 요구사항

배포하는 UI의 `manifest.json`에 다음을 포함하세요:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "A beautiful custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

- `name`과 `version`은 필수입니다
- `name`은 설치 디렉토리 이름이 됩니다
- `"default"`는 예약된 이름이므로 사용할 수 없습니다
