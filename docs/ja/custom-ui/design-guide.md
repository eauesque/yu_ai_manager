# Design Guide — CSS 設計・テーマ・レスポンシブ

カスタム UI のデザインに関するガイドラインと実装パターンです。

## CSS 変数システム

リファレンス UI は CSS カスタムプロパティでテーマを管理しています。
カスタム UI でもこれらの変数を使うことで、テーマ切り替えやダークモード対応が容易になります。

### コア変数

```css
:root {
  --bg: #f5f6f8;         /* ページ背景 */
  --card: #ffffff;        /* カード・パネル背景 */
  --text: #222;           /* メインテキスト */
  --muted: #666;          /* サブテキスト・ヒント */
  --border: #e6e6e6;      /* ボーダー・区切り線 */
  --shadow: 0 4px 14px rgba(0,0,0,0.08);  /* カードシャドウ */
  --btn-bg: #ffffff;      /* ボタン背景 */
  --btn-text: #222;       /* ボタンテキスト */
  --btn-hover: #f6f9ff;   /* ボタンホバー */
  --accent: #2563eb;      /* アクセントカラー (WCAG AA 準拠) */
}
```

### ダークモード変数

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

`color-scheme: dark` は OS のフォームコントロール (チェックボックス、スクロールバー等) の配色に影響します。

### 全変数リスト

詳細は [theming.md](../api/theming.md) を参照してください。

## テーマの作成

### カスタムテーマの定義

テーマは `body` のクラスに紐付けた CSS 変数の上書きで定義します:

```css
/* Ocean テーマ */
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

/* Sakura テーマ (ライトモード) */
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

### テーマの適用

JavaScript でテーマクラスを切り替えます:

```javascript
function setTheme(themeName) {
  // 既存のテーマクラスを除去
  document.body.className = document.body.className
    .replace(/theme-\S+/g, '')
    .trim();
  if (themeName && themeName !== 'default') {
    document.body.classList.add(`theme-${themeName}`);
  }
  // 永続化
  localStorage.setItem('customTheme', themeName);
}

// 起動時に復元
const saved = localStorage.getItem('customTheme');
if (saved) setTheme(saved);
```

### ダークモード切り替え

リファレンス UI のダークモード判定ロジック:

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

## レスポンシブデザイン

### ブレークポイント

リファレンス UI で使用しているブレークポイント:

| ブレークポイント | 用途 |
|----------------|------|
| `max-width: 600px` | モバイル (ハンバーガーメニュー、1列グリッド) |
| `max-width: 900px` | タブレット (2列グリッド、サイドバー折り畳み) |
| `min-width: 901px` | デスクトップ (3列以上グリッド、サイドバー常時表示) |

### グリッドレイアウト

画像検索結果のレスポンシブグリッド:

```css
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 16px;
}

/* モバイル: 小さめのカード */
@media (max-width: 600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
    padding: 8px;
  }
}

/* 大画面: 余裕を持たせる */
@media (min-width: 1600px) {
  .image-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
}
```

### ナビゲーションバー

モバイル対応のナビバー:

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

## コンポーネントパターン

### カードコンポーネント

画像カードの基本パターン:

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

### ボタン

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

/* プライマリボタン */
.btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
.btn-primary:hover {
  filter: brightness(1.1);
}

/* 小さいボタン (補助アクション) */
.btn-sm {
  padding: 4px 10px;
  font-size: 0.8rem;
}
```

### モーダル

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

### タグトークン

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

### トースト通知

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

### スター・レーティング

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
    star.textContent = '★';
    star.onclick = async () => {
      const newRating = i === currentRating ? 0 : i;
      await api('/api/ratings/set', {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId, rating: newRating }),
      });
      // UI を更新
      container.querySelectorAll('.star').forEach((s, idx) => {
        s.classList.toggle('filled', idx < newRating);
      });
    };
    container.appendChild(star);
  }
  return container;
}
```

## パフォーマンス

### 画像の遅延読み込み

```html
<img src="/api/thumbnail/${id}" loading="lazy" alt="${filename}">
```

`loading="lazy"` はブラウザネイティブの遅延読み込み。スクロールで表示領域に入ったときに読み込まれます。

### サムネイルキャッシュ

`/api/thumbnail/<id>` は ETag と 24 時間のキャッシュヘッダを返します。
ブラウザが自動的にキャッシュするため、追加の実装は不要です。

### 大量画像の表示

150,000 件以上のライブラリでは、一度に全件を DOM に追加するとパフォーマンスが低下します。
カーソルベースのページネーションで段階的に読み込むことを推奨:

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

// Intersection Observer でスクロール検出
const sentinel = document.getElementById('sentinel');
new IntersectionObserver(entries => {
  if (entries[0].isIntersecting && nextCursor) loadMore();
}).observe(sentinel);
```

## アクセシビリティ

### カラーコントラスト

- テキスト: WCAG AA (4.5:1 以上) を維持
- `--accent` のデフォルト `#2563eb` は白背景で 5.17:1
- ダークモードの `--accent` `#60a5fa` は暗い背景で十分なコントラスト

### キーボード操作

```css
/* フォーカスリングを視覚化 */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* キーボード以外のフォーカスではリングを非表示 */
:focus:not(:focus-visible) {
  outline: none;
}
```

### スキップリンク

リファレンス UI では画面上部にスキップリンクを配置しています:

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
