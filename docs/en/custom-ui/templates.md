# Templates Guide -- Jinja2 Templates and Page Structure

This guide covers template design for custom UIs.

## Template Engine

YU AI Manager uses the [Jinja2](https://jinja.palletsprojects.com/) template engine. Custom UI templates are processed as Jinja2 as well.

### Jinja2 Basic Syntax

```html
{# Comment #}
{{ variable_name }}
{% if condition %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Page Structure

### Page-to-Route Mapping

Quart routing is fixed. It auto-maps to the following template names:

| Route | Template | Template Variable |
|-------|----------|-------------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

You can use the `active` variable to highlight the current navigation item:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Recommended Page Structure

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
  {# Navigation (when using template splitting) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Page content #}
  </main>

  {# Toast notifications #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Template Splitting Patterns

### Componentization with include

The reference UI splits templates into small partials and assembles them with `{% include %}`:

```
templates/
├── _nav.html              # Shared navbar
├── index.html             # Main page (assembled via includes)
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

Custom UIs can follow the same pattern:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Shared Navbar Example

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

## Plain HTML (without Jinja2)

It is also possible to build a custom UI with plain HTML and JavaScript alone, without using Jinja2 features. Template files are served as-is:

```html
<!-- index.html without Jinja2 syntax -->
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

In this case, JavaScript handles the client-side routing. The server does not serve the same `index.html` for every route. Each page route (`/stats`, `/tools`, etc.) still requires its own template file.

### SPA-like Configuration

You can share the same HTML across all pages by including a common shell from each template:

```html
{# stats.html, tools.html, settings.html, etc. #}
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

JavaScript reads `data-route` to determine and render the appropriate page.

## Internationalization (i18n)

The reference UI supports internationalization through `data-i18n` attributes:

```html
<span data-i18n="nav.search">検索</span>
<input data-i18n-placeholder="search.placeholder" placeholder="タグで検索...">
<button data-i18n-aria-label="nav.menu" aria-label="メニュー">☰</button>
```

A custom UI can use the i18n engine included in the reference UI's `nav.js`, or it can implement its own translation system.

### Simple i18n Implementation Example

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

## Favicon

Place a custom favicon in the `static/` directory:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Quart handles requests to `/favicon.ico` by redirecting to the active UI's `static/favicon.svg`.

## Error Page

An `error.html` template is displayed when a server error occurs:

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

## Default UI Template Inventory

The reference UI template structure (for reference):

| Category | File Count | Description |
|----------|------------|-------------|
| Main pages | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Shared partials | 2 | `_nav.html`, `_ext_nav.html` |
| index partials | 24 | Search form, modals, grid controls, regex panel, etc. |
| settings partials | 5 | Header, tab groups, save bar |
| tools partials | 14 | Search/analysis tools, maintenance, scan settings |
| Other pages | 12 | stats, story, inspect, extensions, share, LAN share |
| **Total** | **66** | -- |

A custom UI does not need to reimplement all of these. You only need to create templates for the pages you want to customize.
