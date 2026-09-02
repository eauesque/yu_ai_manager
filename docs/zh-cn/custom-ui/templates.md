# 模板指南 -- Jinja2 模板与页面结构

本指南介绍自定义 UI 的模板设计。

## 模板引擎

YU AI Manager 使用 [Jinja2](https://jinja.palletsprojects.com/) 模板引擎。自定义 UI 模板也通过 Jinja2 处理。

### Jinja2 基本语法

```html
{# 注释 #}
{{ variable_name }}
{% if condition %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## 页面结构

### 页面到路由的映射

Quart 路由是固定的，自动映射到以下模板名称：

| 路由 | 模板 | 模板变量 |
|------|------|----------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

可以使用 `active` 变量高亮当前导航项：

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### 推荐的页面结构

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
  {# 导航（使用模板分割时）#}
  {% include "_nav.html" %}

  <main id="main-content">
    {# 页面内容 #}
  </main>

  {# 吐司通知 #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## 模板分割模式

### 使用 include 进行组件化

参考 UI 将模板分割为小的局部模板，并使用 `{% include %}` 组合：

```
templates/
├── _nav.html              # 共享导航栏
├── index.html             # 主页面（通过 include 组合）
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

自定义 UI 可以遵循相同的模式：

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### 共享导航栏示例

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

## 纯 HTML（不使用 Jinja2）

也可以不使用 Jinja2 功能，仅用纯 HTML 和 JavaScript 构建自定义 UI。模板文件将原样提供：

```html
<!-- 不含 Jinja2 语法的 index.html -->
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

在这种情况下，JavaScript 处理客户端路由。服务器不会为所有路由提供相同的 `index.html`。每个页面路由（`/stats`、`/tools` 等）仍然需要各自的模板文件。

### SPA 风格配置

可以在每个模板中 include 一个公共外壳，在所有页面共享相同的 HTML：

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

JavaScript 读取 `data-route` 来确定并渲染相应的页面。

## 国际化 (i18n)

参考 UI 通过 `data-i18n` 属性支持国际化：

```html
<span data-i18n="nav.search">検索</span>
<input data-i18n-placeholder="search.placeholder" placeholder="タグで検索...">
<button data-i18n-aria-label="nav.menu" aria-label="メニュー">☰</button>
```

自定义 UI 可以使用参考 UI 的 `nav.js` 中包含的 i18n 引擎，或者实现自己的翻译系统。

### 简单的 i18n 实现示例

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

## 网站图标

将自定义网站图标放在 `static/` 目录中：

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Quart 会将 `/favicon.ico` 请求重定向到活动 UI 的 `static/favicon.svg`。

## 错误页面

服务器发生错误时显示 `error.html` 模板：

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

## 默认 UI 模板清单

参考 UI 模板结构（仅供参考）：

| 类别 | 文件数 | 说明 |
|------|--------|------|
| 主页面 | 9 | index、stats、tools、settings、story、inspect、extensions、share、error |
| 共享局部模板 | 2 | `_nav.html`、`_ext_nav.html` |
| index 局部模板 | 24 | 搜索表单、模态框、网格控件、正则面板等 |
| settings 局部模板 | 5 | 头部、标签组、保存栏 |
| tools 局部模板 | 14 | 搜索/分析工具、维护、扫描设置 |
| 其他页面 | 12 | stats、story、inspect、extensions、share、LAN share |
| **总计** | **66** | -- |

自定义 UI 不需要重新实现所有这些。您只需为想要自定义的页面创建模板即可。
