# 디자인 가이드 -- CSS 디자인, 테마, 반응형 레이아웃

이 가이드는 커스텀 UI를 위한 디자인 가이드라인과 구현 패턴을 제공합니다.

## CSS 변수 시스템

레퍼런스 UI는 CSS 커스텀 프로퍼티를 통해 테마를 관리합니다. 커스텀 UI에서도 동일한 변수를 사용하여 테마 전환과 다크 모드 지원을 간단하게 할 수 있습니다.

### 핵심 변수

```css
:root {
  --bg: #f5f6f8;         /* 페이지 배경 */
  --card: #ffffff;        /* 카드 / 패널 배경 */
  --text: #222;           /* 메인 텍스트 */
  --muted: #666;          /* 보조 텍스트 / 힌트 */
  --border: #e6e6e6;      /* 테두리 / 구분선 */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* 카드 그림자 */
  --btn-bg: #ffffff;      /* 버튼 배경 */
  --btn-text: #222;       /* 버튼 텍스트 */
  --btn-hover: #f6f9ff;   /* 버튼 호버 */
  --accent: #2563eb;      /* 강조 색상 (WCAG AA 준수) */
}
```

### 다크 모드 변수

```css
body.dark {
  --bg: #0f1115;
  --card: #1b1f2a;
  --text: #e7eaf0;
  --muted: #aab2c0;
  --border: #2b3240;
  --shadow: 0 10px 26px rgba(0,0,0,0.45);
  --btn-bg: #1b2030;
  --btn-text: #e7eaf0;
  --btn-hover: #222a3d;
  --accent: #60a5fa;
  color-scheme: dark;
}
```

`color-scheme: dark` 선언은 OS 수준의 폼 컨트롤(체크박스, 스크롤바 등)에 영향을 줍니다.

### 전체 변수 목록

전체 목록은 [theming.md](../api/theming.md)를 참조하세요.

## 테마 만들기

### 커스텀 테마 정의

테마는 `body` 클래스에 CSS 변수를 덮어써서 정의합니다:

```css
/* Ocean 테마 */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --muted: #7a9cc0;
  --border: #1e3a5f;
  --shadow: 0 8px 24px rgba(0,0,0,0.5);
  --btn-bg: #1a3050;
  --btn-text: #c8daf0;
  --btn-hover: #243d5f;
  --accent: #38bdf8;
  color-scheme: dark;
}

/* Sakura 테마 (라이트 모드) */
body.theme-sakura {
  --bg: #fff5f5;
  --card: #ffffff;
  --text: #4a3030;
  --muted: #8a7070;
  --border: #f0d0d0;
  --shadow: 0 4px 14px rgba(200,100,100,0.1);
  --accent: #e8457a;
  color-scheme: light;
}
```

### 테마 적용

JavaScript로 테마 클래스를 전환합니다:

```javascript
function setTheme(themeName) {
  // 기존 테마 클래스 제거
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // 저장
  localStorage.setItem('customTheme', themeName);
}

// 시작 시 복원
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### 다크 모드 토글

레퍼런스 UI는 다크 모드 감지에 다음 로직을 사용합니다:

```javascript
function initDarkMode() {
  const saved = localStorage.getItem('darkMode');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved !== null ? saved === 'true' : prefersDark;
  document.body.classList.toggle('dark', isDark);
}

function toggleDarkMode() {
  const isDark = document.body.classList.toggle('dark');
  localStorage.setItem('darkMode', String(isDark));
}

initDarkMode();
```

## 반응형 디자인

### 브레이크포인트

레퍼런스 UI는 다음 브레이크포인트를 사용합니다:

| 브레이크포인트 | 용도 |
|----------------|------|
| `max-width: 600px` | 모바일 (햄버거 메뉴, 단일 열 그리드) |
| `max-width: 900px` | 태블릿 (2열 그리드, 접이식 사이드바) |
| `min-width: 901px` | 데스크톱 (3열 이상 그리드, 항상 보이는 사이드바) |

### 그리드 레이아웃

이미지 검색 결과를 위한 반응형 그리드:

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* 모바일: 작은 카드 */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* 대형 화면: 여유있는 간격 */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### 네비게이션 바

모바일 친화적 네비게이션 바:

```css
.navbar {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-links {
  display: flex;
  gap: 8px;
}

.hamburger { display: none; }

@media (max-width: 600px) {
  .nav-links {
    display: none;
    position: absolute;
    top: 48px;
    left: 0;
    right: 0;
    flex-direction: column;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 8px;
  }
  .nav-links.open { display: flex; }
  .hamburger { display: block; }
}
```

## 컴포넌트 패턴

### 카드 컴포넌트

기본 이미지 카드 패턴:

```css
.card {
  background: var(--card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: var(--shadow);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.3);
}

.card img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
}

.card-body {
  padding: 10px 12px;
}

.card-title {
  font-size: 0.85rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 2px;
}
```

### 버튼

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--btn-bg);
  color: var(--btn-text);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: background 0.15s;
}

.btn:hover { background: var(--btn-hover); }

/* 주요 버튼 */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* 작은 버튼 (보조 동작) */
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### 모달

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.modal-overlay.active {
  opacity: 1;
  pointer-events: auto;
}

.modal {
  background: var(--card);
  border-radius: 12px;
  padding: 24px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 1.5rem;
  cursor: pointer;
}
```

### 태그 토큰

```css
.tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--tag-bg, #4a4a4a);
  color: var(--tag-text, #f0f0f0);
  border: 1px solid var(--tag-border, #666);
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.1s;
}

.tag:hover {
  background: var(--tag-hover-bg, #5a5a5a);
  border-color: var(--tag-hover-border, #888);
}
```

### 토스트 알림

```css
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(100px);
  background: var(--card);
  color: var(--text);
  padding: 12px 24px;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 2000;
  opacity: 0;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.toast.show {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}
```

```javascript
function showToast(message, duration = 3000) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}
```

### 별점 평가

```css
.star-rating {
  display: inline-flex;
  gap: 2px;
}

.star-rating .star {
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--muted);
  transition: color 0.1s;
}

.star-rating .star.filled { color: #fbbf24; }
.star-rating .star:hover { color: #f59e0b; }
```

```javascript
function createStarRating(fileId, currentRating = 0) {
  const container = document.createElement('div');
  container.className = 'star-rating';
  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'star' + (i <= currentRating ? ' filled' : '');
    star.textContent = '\u2605';
    star.onclick = async () => {
      const newRating = i === currentRating ? 0 : i;
      await api('/api/ratings/set', {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId, rating: newRating }),
      });
      // UI 업데이트
      container.querySelectorAll('.star').forEach((s, idx) => {
        s.classList.toggle('filled', idx < newRating);
      });
    };
    container.appendChild(star);
  }
  return container;
}
```

## 성능

### 이미지 지연 로딩

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` 속성은 브라우저 네이티브 지연 로딩을 활성화합니다. 브라우저는 이미지가 뷰포트에 들어올 때만 로드합니다.

### 썸네일 캐싱

`/api/thumbnail/<id>`는 ETag와 24시간 캐시 헤더를 반환합니다. 브라우저가 썸네일을 자동으로 캐시하므로 추가 구현이 필요 없습니다.

### 대규모 컬렉션 표시

150,000개 이상의 항목이 있는 라이브러리에서 모든 항목을 한 번에 DOM에 추가하면 성능이 저하됩니다. 커서 기반 페이지네이션으로 점진적으로 항목을 로드하는 것이 좋습니다:

```javascript
let nextCursor = null;
let loading = false;

async function loadMore() {
  if (loading) return;
  loading = true;
  const params = new URLSearchParams({ limit: '50' });
  if (nextCursor) params.set('cursor', nextCursor);
  const res = await fetch(`/api/search?${params}`);
  const json = await res.json();
  const items = json.results || json.data?.results || [];
  nextCursor = json.next_cursor || json.data?.next_cursor || null;

  const grid = document.getElementById('results');
  items.forEach(f => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `<img src="/api/thumbnail/${f.id}" loading="lazy">`;
    grid.appendChild(card);
  });
  loading = false;
}

// Intersection Observer로 스크롤 감지
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## 접근성

### 색상 대비

- 텍스트는 WCAG AA (최소 4.5:1)를 유지해야 합니다
- 기본 `--accent` 값 `#2563eb`은 흰색 배경에서 5.17:1을 달성합니다
- 다크 모드 `--accent` 값 `#60a5fa`는 어두운 배경에서 충분한 대비를 제공합니다

### 키보드 내비게이션

```css
/* 포커스 링 표시 */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 비키보드 상호작용에서는 포커스 링 숨기기 */
:focus:not(:focus-visible) {
  outline: none;
}
```

### 건너뛰기 링크

레퍼런스 UI는 페이지 상단에 건너뛰기 링크를 배치합니다:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

```css
.skip-link {
  position: absolute;
  top: -100px;
  left: 16px;
  z-index: 9999;
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border-radius: 4px;
}
.skip-link:focus { top: 8px; }
```
