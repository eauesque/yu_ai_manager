# Templates-Leitfaden — Jinja2-Templates und Seitenstruktur

Leitfaden zum Template-Design für benutzerdefinierte UIs.

## Template-Engine

YU AI Manager verwendet die [Jinja2](https://jinja.palletsprojects.com/)-Template-Engine.
Templates benutzerdefinierter UIs werden ebenfalls als Jinja2 verarbeitet.

### Jinja2-Grundsyntax

```html
{# Kommentar #}
{{ Variablenname }}
{% if Bedingung %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Seitenstruktur

### Zuordnung von Seiten zu Routen

Das Quart-Routing ist fest und wird automatisch den folgenden Template-Namen zugeordnet:

| Route | Template | Template-Variablen |
|--------|------------|----------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

Die Variable `active` kann für den Aktiv-Status der Navigation verwendet werden:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Empfohlene Seitenstruktur

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Navigation (bei Template-Aufteilung) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Seiteninhalt #}
  </main>

  {# Toast-Benachrichtigungen #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Template-Aufteilungsmuster

### Modularisierung mit include

Die Referenz-UI teilt Templates in kleine Teile auf und kombiniert sie mit `{% include %}`:

```
templates/
├── _nav.html              # Gemeinsame Navigationsleiste
├── index.html             # Hauptseite (per include aufgebaut)
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

Dasselbe Muster kann in benutzerdefinierten UIs verwendet werden:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Beispiel einer gemeinsamen Navigationsleiste

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

## Reines HTML (ohne Jinja2)

Eine benutzerdefinierte UI kann auch nur mit reinem HTML + JavaScript ohne Jinja2-Funktionen gebaut werden.
Template-Dateien werden dann direkt als HTML geliefert.

In diesem Fall wird das Routing auf der JavaScript-Seite gesteuert, und für jede Seiten-Route (`/stats`, `/tools` usw.) wird eine eigene Template-Datei benötigt.

### SPA-ähnliche Konfiguration

Wenn dieselbe HTML für alle Seiten verwendet werden soll, das gemeinsame HTML aus jedem Template einbinden:

```html
{# stats.html, tools.html, settings.html usw. #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`:
```html
<!DOCTYPE html>
<html lang="de">
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

Auf JavaScript-Seite `data-route` auslesen, um Seiten umzuschalten.

## Internationalisierung (i18n)

Die Referenz-UI unterstützt Internationalisierung über das `data-i18n`-Attribut:

```html
<span data-i18n="nav.search">Suche</span>
<input data-i18n-placeholder="search.placeholder" placeholder="Nach Tags suchen...">
<button data-i18n-aria-label="nav.menu" aria-label="Menü">☰</button>
```

Wenn i18n in der benutzerdefinierten UI verwendet werden soll, kann entweder die i18n-Engine aus `nav.js` der Referenz-UI genutzt oder ein eigenes Übersetzungssystem implementiert werden.

### Einfaches i18n-Implementierungsbeispiel

```javascript
const translations = {
  de: { 'search': 'Suche', 'stats': 'Statistiken', 'settings': 'Einstellungen' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['de'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## Favicon

Um ein eigenes Favicon in der benutzerdefinierten UI zu platzieren, in `static/` ablegen:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Anfragen an `/favicon.ico` werden von der Quart-Route verarbeitet und auf `static/favicon.svg` der aktiven UI weitergeleitet.

## Fehlerseite

Wenn ein `error.html`-Template vorhanden ist, wird es bei Server-Fehlern angezeigt:

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="de">
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

## Template-Liste der Standard-UI

Template-Struktur der Referenz-UI (zur Referenz):

| Kategorie | Anzahl Dateien | Beschreibung |
|---------|----------|------|
| Hauptseiten | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Gemeinsame Teile | 2 | `_nav.html`, `_ext_nav.html` |
| index-Aufteilung | 24 | Suchformular, Modale, Raster-Steuerung, Regex-Panel usw. |
| settings-Aufteilung | 5 | Header, Tab-Gruppen, Speicherleiste |
| tools-Aufteilung | 14 | Such- und Analysetools, Wartung, Scan-Einstellungen |
| Sonstige Seiten | 12 | stats, story, inspect, extensions, share, LAN Share |
| **Gesamt** | **66** | — |

Benutzerdefinierte UIs müssen nicht alle diese neu implementieren.
Es müssen nur Templates für die benötigten Seiten erstellt werden.
