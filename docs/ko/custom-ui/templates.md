# 템플릿 가이드 -- Jinja2 템플릿과 페이지 구조

이 가이드는 커스텀 UI의 템플릿 설계를 다룹니다.

## 템플릿 엔진

YU AI Manager는 [Jinja2](https://jinja.palletsprojects.com/) 템플릿 엔진을 사용합니다. 커스텀 UI 템플릿도 Jinja2로 처리됩니다.

### Jinja2 기본 구문

```html
{# 주석 #}
{{ variable_name }}
{% if condition %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## 페이지 구조

### 페이지-라우트 매핑

Quart 라우팅은 고정되어 있으며, 다음 템플릿 이름에 자동 매핑됩니다:

| 라우트 | 템플릿 | 템플릿 변수 |
|--------|--------|-------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

`active` 변수를 사용하여 현재 네비게이션 항목을 강조할 수 있습니다:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### 권장 페이지 구조

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
  {# 네비게이션 (템플릿 분할 사용 시) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# 페이지 콘텐츠 #}
  </main>

  {# 토스트 알림 #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## 템플릿 분할 패턴

### include를 이용한 컴포넌트화

레퍼런스 UI는 템플릿을 작은 파셜로 분할하고 `{% include %}`로 조합합니다:

```
templates/
├── _nav.html              # 공유 네비게이션 바
├── index.html             # 메인 페이지 (include로 조합)
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

커스텀 UI도 동일한 패턴을 따를 수 있습니다:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### 공유 네비게이션 바 예시

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

## 순수 HTML (Jinja2 없이)

Jinja2 기능을 사용하지 않고 순수 HTML과 JavaScript만으로 커스텀 UI를 구축할 수도 있습니다. 템플릿 파일은 그대로 제공됩니다:

```html
<!-- Jinja2 구문 없는 index.html -->
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

이 경우 JavaScript가 클라이언트 사이드 라우팅을 처리합니다. 서버는 모든 라우트에 동일한 `index.html`을 제공하지 않습니다. 각 페이지 라우트(`/stats`, `/tools` 등)에는 여전히 고유한 템플릿 파일이 필요합니다.

### SPA 유사 구성

각 템플릿에서 공통 셸을 include하여 모든 페이지에서 동일한 HTML을 공유할 수 있습니다:

```html
{# stats.html, tools.html, settings.html 등 #}
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

JavaScript가 `data-route`를 읽어 적절한 페이지를 결정하고 렌더링합니다.

## 국제화 (i18n)

레퍼런스 UI는 `data-i18n` 속성을 통해 국제화를 지원합니다:

```html
<span data-i18n="nav.search">검색</span>
<input data-i18n-placeholder="search.placeholder" placeholder="タグで検索...">
<button data-i18n-aria-label="nav.menu" aria-label="メニュー">☰</button>
```

커스텀 UI는 레퍼런스 UI의 `nav.js`에 포함된 i18n 엔진을 사용하거나 자체 번역 시스템을 구현할 수 있습니다.

### 간단한 i18n 구현 예시

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

## 파비콘

`static/` 디렉토리에 커스텀 파비콘을 배치합니다:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Quart는 `/favicon.ico` 요청을 활성 UI의 `static/favicon.svg`로 리디렉션합니다.

## 오류 페이지

서버 오류 발생 시 `error.html` 템플릿이 표시됩니다:

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

## 기본 UI 템플릿 목록

레퍼런스 UI 템플릿 구조 (참고용):

| 카테고리 | 파일 수 | 설명 |
|----------|---------|------|
| 메인 페이지 | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| 공유 파셜 | 2 | `_nav.html`, `_ext_nav.html` |
| index 파셜 | 24 | 검색 폼, 모달, 그리드 컨트롤, regex 패널 등 |
| settings 파셜 | 5 | 헤더, 탭 그룹, 저장 바 |
| tools 파셜 | 14 | 검색/분석 도구, 유지보수, 스캔 설정 |
| 기타 페이지 | 12 | stats, story, inspect, extensions, share, LAN share |
| **합계** | **66** | -- |

커스텀 UI에서 이 모든 것을 다시 구현할 필요는 없습니다. 커스터마이징하려는 페이지의 템플릿만 만들면 됩니다.
