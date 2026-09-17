# Templates Guide — Jinja2 テンプレートとページ構造

カスタム UI のテンプレート設計に関するガイドです。

## テンプレートエンジン

YU AI Manager は [Jinja2](https://jinja.palletsprojects.com/) テンプレートエンジンを使用しています。
カスタム UI のテンプレートも Jinja2 として処理されます。

### Jinja2 の基本構文

```html
{# コメント #}
{{ 変数名 }}
{% if 条件 %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## ページ構造

### ページとルートの対応

Quart のルーティングは固定されており、以下のテンプレート名に自動マッピングされます:

| ルート | テンプレート | テンプレート変数 |
|--------|------------|----------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

`active` 変数はナビゲーションのアクティブ状態に使用できます:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### 推奨ページ構造

```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# ナビゲーション (テンプレート分割の場合) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# ページコンテンツ #}
  </main>

  {# トースト通知用 #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## テンプレート分割パターン

### include による部品化

リファレンス UI はテンプレートを細かく分割し `{% include %}` で結合しています:

```
templates/
├── _nav.html              # 共通ナビバー
├── index.html             # メインページ (include で組み立て)
├── index/
│   ├── _main_container.html
│   ├── _search_modal.html
│   └── main_container/
│       ├── _search_form_main_row.html
│       └── _results_and_loading.html
├── settings.html
├── settings/
│   ├── _content.html
│   └── content/
│       ├── _header_server.html
│       └── _tabs_misc.html
└── stats.html
```

カスタム UI でも同じパターンが使えます:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### 共通ナビバーの例

`templates/_nav.html`:

```html
<nav class="navbar">
  <a href="/" class="nav-brand">My UI</a>
  <div class="nav-links">
    <a href="/" class="nav-link{% if active == 'search' %} active{% endif %}">
      Search
    </a>
    <a href="/stats" class="nav-link{% if active == 'stats' %} active{% endif %}">
      Stats
    </a>
    <a href="/tools" class="nav-link{% if active == 'tools' %} active{% endif %}">
      Tools
    </a>
    <a href="/settings" class="nav-link{% if active == 'settings' %} active{% endif %}">
      Settings
    </a>
  </div>
  <button id="themeToggle" onclick="toggleDarkMode()">🌙</button>
</nav>
```

## 純粋な HTML (Jinja2 不使用)

Jinja2 の機能を使わず、純粋な HTML + JavaScript だけでカスタム UI を構築することも可能です。
テンプレートファイルはそのまま HTML として配信されます:

```html
<!-- Jinja2 構文を使わない index.html -->
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>SPA Custom UI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

この場合、ルーティングは JavaScript 側で制御し、サーバー側のルートは
すべて同じ `index.html` を返す形にはなりません。
各ページルート (`/stats`, `/tools` 等) にはそれぞれテンプレートファイルが必要です。

### SPA ライクな構成

すべてのページで同じ HTML を使いたい場合は、各テンプレートから共通の HTML を include します:

```html
{# stats.html, tools.html, settings.html 等 #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`:
```html
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>My SPA UI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div id="app" data-route="{{ active }}"></div>
  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

JavaScript 側で `data-route` を読み取ってページを切り替えます。

## 国際化 (i18n)

リファレンス UI は `data-i18n` 属性による国際化をサポートしています:

```html
<span data-i18n="nav.search">検索</span>
<input data-i18n-placeholder="search.placeholder" placeholder="タグで検索...">
<button data-i18n-aria-label="nav.menu" aria-label="メニュー">☰</button>
```

カスタム UI で i18n を使う場合は、リファレンス UI の `nav.js` に含まれる
i18n エンジンを利用するか、独自の翻訳システムを実装できます。

### シンプルな i18n 実装例

```javascript
const translations = {
  ja: { 'search': '検索', 'stats': '統計', 'settings': '設定' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['ja'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## favicon

カスタム UI に独自のファビコンを配置する場合は `static/` に配置します:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

`/favicon.ico` へのリクエストは Quart のルートで処理され、
アクティブ UI の `static/favicon.svg` にリダイレクトされます。

## エラーページ

`error.html` テンプレートを配置すると、サーバーエラー時に表示されます:

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>Error</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  <main style="text-align: center; padding: 60px 20px;">
    <h1>Something went wrong</h1>
    <p>Please try again later.</p>
    <a href="/">Back to Home</a>
  </main>
</body>
</html>
```

## デフォルト UI テンプレート一覧

リファレンス UI のテンプレート構成 (参考):

| カテゴリ | ファイル数 | 説明 |
|---------|----------|------|
| メインページ | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| 共通部品 | 2 | `_nav.html`, `_ext_nav.html` |
| index 分割 | 24 | 検索フォーム、モーダル、グリッド制御、正規表現パネル等 |
| settings 分割 | 5 | ヘッダー、タブ群、保存バー |
| tools 分割 | 14 | 検索・分析ツール、メンテナンス、スキャン設定 |
| その他ページ | 12 | stats, story, inspect, extensions, share, LAN share |
| **合計** | **66** | — |

カスタム UI はこれらすべてを再実装する必要はありません。
必要なページだけテンプレートを作成すれば、そのページのみカスタム表示されます。
