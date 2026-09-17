# 設計指南 -- CSS 設計、主題與響應式佈局

本指南為自訂 UI 提供設計準則和實作模式。

## CSS 變數系統

參考 UI 透過 CSS 自訂屬性管理主題。自訂 UI 可以使用相同的變數來簡化主題切換和深色模式支援。

### 核心變數

```css
:root {
  --bg: #f5f6f8;         /* 頁面背景 */
  --card: #ffffff;        /* 卡片 / 面板背景 */
  --text: #222;           /* 主文字 */
  --muted: #666;          /* 輔助文字 / 提示 */
  --border: #e6e6e6;      /* 邊框 / 分隔線 */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* 卡片陰影 */
  --btn-bg: #ffffff;      /* 按鈕背景 */
  --btn-text: #222;       /* 按鈕文字 */
  --btn-hover: #f6f9ff;   /* 按鈕懸停 */
  --accent: #2563eb;      /* 強調色（WCAG AA 合規） */
}
```

### 深色模式變數

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

`color-scheme: dark` 宣告會影響作業系統層級的表單控制項（核取方塊、捲軸等）。

### 完整變數清單

完整清單請參閱 [theming.md](../api/theming.md)。

## 建立主題

### 定義自訂主題

透過在 `body` 類別上覆寫 CSS 變數來定義主題：

```css
/* Ocean 主題 */
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

/* Sakura 主題（淺色模式）*/
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

### 套用主題

使用 JavaScript 切換主題類別：

```javascript
function setTheme(themeName) {
  // 移除現有主題類別
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // 持久化
  localStorage.setItem('customTheme', themeName);
}

// 啟動時還原
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### 深色模式切換

參考 UI 使用以下邏輯進行深色模式偵測：

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

## 響應式設計

### 中斷點

參考 UI 使用以下中斷點：

| 中斷點 | 用途 |
|--------|------|
| `max-width: 600px` | 行動裝置（漢堡選單、單欄格線） |
| `max-width: 900px` | 平板（雙欄格線、可摺疊側邊欄） |
| `min-width: 901px` | 桌面（三欄或更寬格線、始終可見的側邊欄） |

### 格線佈局

圖片搜尋結果的響應式格線：

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* 行動裝置：更小的卡片 */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* 大螢幕：更寬裕的間距 */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### 導覽列

行動裝置友善的導覽列：

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

## 元件模式

### 卡片元件

基本圖片卡片模式：

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

### 按鈕

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

/* 主要按鈕 */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* 小按鈕（輔助操作）*/
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### 模態框

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

### 標籤令牌

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

### 吐司通知

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

### 星級評分

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
      // 更新 UI
      container.querySelectorAll('.star').forEach((s, idx) => {
        s.classList.toggle('filled', idx < newRating);
      });
    };
    container.appendChild(star);
  }
  return container;
}
```

## 效能

### 圖片延遲載入

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` 屬性啟用瀏覽器原生延遲載入。瀏覽器僅在圖片進入可視區域時才載入。

### 縮圖快取

`/api/thumbnail/<id>` 回傳 ETag 和 24 小時快取標頭。瀏覽器自動快取縮圖，無需額外實作。

### 顯示大型收藏

超過 150,000 項的圖庫在一次性將所有項新增到 DOM 時會出現效能下降。建議使用基於游標的分頁逐步載入：

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

// 使用 Intersection Observer 偵測捲動
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## 無障礙

### 色彩對比度

- 文字必須維持 WCAG AA（最低 4.5:1）
- 預設 `--accent` 值 `#2563eb` 在白色背景上達到 5.17:1
- 深色模式 `--accent` 值 `#60a5fa` 在深色背景上提供充足的對比度

### 鍵盤導覽

```css
/* 可見的焦點環 */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 非鍵盤互動時隱藏焦點環 */
:focus:not(:focus-visible) {
  outline: none;
}
```

### 跳轉連結

參考 UI 在頁面頂部放置了一個跳轉連結：

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
