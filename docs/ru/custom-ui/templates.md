# Руководство по шаблонам — Jinja2 и структура страниц

Руководство по дизайну шаблонов пользовательского UI.

## Шаблонный движок

YU AI Manager использует шаблонный движок [Jinja2](https://jinja.palletsprojects.com/).
Шаблоны пользовательского UI также обрабатываются через Jinja2.

### Базовый синтаксис Jinja2

```html
{# Комментарий #}
{{ имя_переменной }}
{% if условие %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Структура страниц

### Соответствие страниц и маршрутов

Маршрутизация Quart фиксирована и автоматически отображается на следующие имена шаблонов:

| Маршрут | Шаблон | Переменные шаблона |
|---------|--------|--------------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

Переменная `active` может использоваться для состояния активного элемента навигации:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Рекомендуемая структура страницы

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Навигация (при разбивке на части) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Содержимое страницы #}
  </main>

  {# Для toast-уведомлений #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Паттерны разбивки шаблонов

### Разбивка на части через include

Референсный UI разбивает шаблоны на мелкие части и объединяет их через `{% include %}`:

```
templates/
├── _nav.html              # Общая навбар
├── index.html             # Главная страница (собирается через include)
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

Тот же паттерн можно использовать в пользовательском UI:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Пример общей навбар

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
  <button id="themeToggle">🌙</button>
</nav>
```

## Чистый HTML (без Jinja2)

Пользовательский UI можно создать исключительно на HTML + JavaScript, без функций Jinja2.
Файлы шаблонов будут отдаваться как обычный HTML:

```html
<!-- index.html без синтаксиса Jinja2 -->
<!DOCTYPE html>
<html lang="ru">
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

В этом случае маршрутизация управляется на стороне JavaScript, однако сервер
не будет возвращать один и тот же `index.html` для всех маршрутов.
Для каждого маршрута страницы (`/stats`, `/tools` и т.д.) требуется отдельный файл шаблона.

### Конфигурация SPA-подобного UI

Для использования одного HTML на всех страницах — подключайте общий HTML из каждого шаблона:

```html
{# stats.html, tools.html, settings.html и т.д. #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`:
```html
<!DOCTYPE html>
<html lang="ru">
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

На стороне JavaScript читайте `data-route` и переключайте страницы соответственно.

## Интернационализация (i18n)

Референсный UI поддерживает интернационализацию через атрибут `data-i18n`:

```html
<span data-i18n="nav.search">Поиск</span>
<input data-i18n-placeholder="search.placeholder" placeholder="Поиск по тегам...">
<button data-i18n-aria-label="nav.menu" aria-label="Меню">☰</button>
```

Для i18n в пользовательском UI можно использовать движок i18n из `nav.js` референсного UI
или реализовать собственную систему перевода.

### Простой пример реализации i18n

```javascript
const translations = {
  ru: { 'search': 'Поиск', 'stats': 'Статистика', 'settings': 'Настройки' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['ru'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## Favicon

Для размещения собственного favicon в пользовательском UI поместите его в `static/`:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Запросы к `/favicon.ico` обрабатываются маршрутом Quart
и перенаправляются на `static/favicon.svg` активного UI.

## Страница ошибок

Если разместить шаблон `error.html`, он будет отображаться при серверных ошибках:

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="ru">
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

## Список шаблонов стандартного UI

Структура шаблонов референсного UI (для справки):

| Категория | Файлов | Описание |
|-----------|--------|----------|
| Главные страницы | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Общие части | 2 | `_nav.html`, `_ext_nav.html` |
| Разбивка index | 24 | форма поиска, модальные окна, управление сеткой, панель regex и т.д. |
| Разбивка settings | 5 | заголовок, вкладки, панель сохранения |
| Разбивка tools | 14 | инструменты поиска/анализа, обслуживание, настройки сканирования |
| Остальные страницы | 12 | stats, story, inspect, extensions, share, LAN share |
| **Итого** | **66** | — |

Пользовательскому UI не нужно реализовывать все эти шаблоны.
Достаточно создать шаблоны только для нужных страниц.
