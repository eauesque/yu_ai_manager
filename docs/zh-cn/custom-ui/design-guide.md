# 设计指南 -- CSS 设计、主题与响应式布局

本指南为自定义 UI 提供设计准则和实现模式。

## CSS 变量系统

参考 UI 通过 CSS 自定义属性管理主题。自定义 UI 可以使用相同的变量来简化主题切换和深色模式支持。

### 核心变量

```css
:root {
  --bg: #f5f6f8;         /* 页面背景 */
  --card: #ffffff;        /* 卡片 / 面板背景 */
  --text: #222;           /* 主文本 */
  --muted: #666;          /* 辅助文本 / 提示 */
  --border: #e6e6e6;      /* 边框 / 分隔线 */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* 卡片阴影 */
  --btn-bg: #ffffff;      /* 按钮背景 */
  --btn-text: #222;       /* 按钮文本 */
  --btn-hover: #f6f9ff;   /* 按钮悬停 */
  --accent: #2563eb;      /* 强调色（WCAG AA 合规） */
}
```

### 深色模式变量

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

`color-scheme: dark` 声明会影响操作系统级别的表单控件（复选框、滚动条等）。

### 完整变量列表

完整列表请参阅 [theming.md](../api/theming.md)。

## 创建主题

### 定义自定义主题

通过在 `body` 类上覆盖 CSS 变量来定义主题：

```css
/* Ocean 主题 */
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

/* Sakura 主题（浅色模式）*/
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

### 应用主题

使用 JavaScript 切换主题类：

```javascript
function setTheme(themeName) {
  // 移除现有主题类
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // 持久化
  localStorage.setItem('customTheme', themeName);
}

// 启动时恢复
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### 深色模式切换

参考 UI 使用以下逻辑进行深色模式检测：

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

## 响应式设计

### 断点

参考 UI 使用以下断点：

| 断点 | 用途 |
|------|------|
| `max-width: 600px` | 移动端（汉堡菜单、单列网格） |
| `max-width: 900px` | 平板（两列网格、可折叠侧边栏） |
| `min-width: 901px` | 桌面端（三列或更宽网格、始终可见的侧边栏） |

### 网格布局

图片搜索结果的响应式网格：

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* 移动端：更小的卡片 */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* 大屏幕：更宽裕的间距 */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### 导航栏

移动端友好的导航栏：

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

## 组件模式

### 卡片组件

基本图片卡片模式：

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

### 按钮

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

/* 主要按钮 */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* 小按钮（辅助操作）*/
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### 模态框

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

### 标签令牌

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

### 星级评分

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

## 性能

### 图片懒加载

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` 属性启用浏览器原生懒加载。浏览器仅在图片进入视口时才加载。

### 缩略图缓存

`/api/thumbnail/<id>` 返回 ETag 和 24 小时缓存头。浏览器自动缓存缩略图，无需额外实现。

### 显示大型收藏

超过 150,000 项的图库在一次性将所有项添加到 DOM 时会出现性能下降。建议使用基于游标的分页逐步加载：

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

// 使用 Intersection Observer 检测滚动
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## 无障碍

### 颜色对比度

- 文本必须保持 WCAG AA（最低 4.5:1）
- 默认 `--accent` 值 `#2563eb` 在白色背景上达到 5.17:1
- 深色模式 `--accent` 值 `#60a5fa` 在深色背景上提供充足的对比度

### 键盘导航

```css
/* 可见的焦点环 */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 非键盘交互时隐藏焦点环 */
:focus:not(:focus-visible) {
  outline: none;
}
```

### 跳转链接

参考 UI 在页面顶部放置了一个跳转链接：

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
