# 範本指南 -- Jinja2 範本與頁面結構

本指南介紹自訂 UI 的範本設計。

## 範本引擎

YU AI Manager 使用 [Jinja2](https://jinja.palletsprojects.com/) 範本引擎。自訂 UI 範本也透過 Jinja2 處理。

### Jinja2 基本語法

```html
{# 註解 #}
{{ variable_name }}
{% if condition %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## 頁面結構

### 頁面到路由的對應

Quart 路由是固定的，自動對應到以下範本名稱：

| 路由 | 範本 | 範本變數 |
|------|------|----------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

可以使用 `active` 變數標示目前的導覽項目：

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### 建議的頁面結構

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
  {# 導覽（使用範本分割時）#}
  {% include "_nav.html" %}

  <main id="main-content">
    {# 頁面內容 #}
  </main>

  {# 吐司通知 #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## 範本分割模式

### 使用 include 進行元件化

參考 UI 將範本分割為小的局部範本，並使用 `{% include %}` 組合：

```
templates/
├── _nav.html              # 共用導覽列
├── index.html             # 主頁面（透過 include 組合）
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

自訂 UI 可以遵循相同的模式：

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### 共用導覽列範例

`templates/_nav.html`：

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

## 純 HTML（不使用 Jinja2）

也可以不使用 Jinja2 功能，僅用純 HTML 和 JavaScript 建構自訂 UI。範本檔案將原樣提供：

```html
<!-- 不含 Jinja2 語法的 index.html -->
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

在這種情況下，JavaScript 處理用戶端路由。伺服器不會為所有路由提供相同的 `index.html`。每個頁面路由（`/stats`、`/tools` 等）仍然需要各自的範本檔案。

### SPA 風格設定

可以在每個範本中 include 一個共用外殼，在所有頁面共享相同的 HTML：

```html
{# stats.html、tools.html、settings.html 等 #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`：
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

JavaScript 讀取 `data-route` 來決定並呈現相應的頁面。

## 國際化 (i18n)

參考 UI 透過 `data-i18n` 屬性支援國際化：

```html
<span data-i18n="nav.search">検索</span>
<input data-i18n-placeholder="search.placeholder" placeholder="タグで検索...">
<button data-i18n-aria-label="nav.menu" aria-label="メニュー">☰</button>
```

自訂 UI 可以使用參考 UI 的 `nav.js` 中包含的 i18n 引擎，或者實作自己的翻譯系統。

### 簡單的 i18n 實作範例

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

## 網站圖示

將自訂網站圖示放在 `static/` 目錄中：

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Quart 會將 `/favicon.ico` 請求重新導向到使用中的 UI 的 `static/favicon.svg`。

## 錯誤頁面

伺服器發生錯誤時顯示 `error.html` 範本：

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

## 預設 UI 範本清單

參考 UI 範本結構（僅供參考）：

| 類別 | 檔案數 | 說明 |
|------|--------|------|
| 主頁面 | 9 | index、stats、tools、settings、story、inspect、extensions、share、error |
| 共用局部範本 | 2 | `_nav.html`、`_ext_nav.html` |
| index 局部範本 | 24 | 搜尋表單、模態框、格線控制項、正規表示式面板等 |
| settings 局部範本 | 5 | 標頭、標籤群組、儲存列 |
| tools 局部範本 | 14 | 搜尋/分析工具、維護、掃描設定 |
| 其他頁面 | 12 | stats、story、inspect、extensions、share、LAN share |
| **總計** | **66** | -- |

自訂 UI 不需要重新實作所有這些。您只需為想要自訂的頁面建立範本即可。
