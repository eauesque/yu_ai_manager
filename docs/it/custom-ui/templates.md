# Guida ai template — Template Jinja2 e struttura pagine

Guida alla progettazione dei template per un'UI personalizzata.

## Motore template

YU AI Manager usa il motore template [Jinja2](https://jinja.palletsprojects.com/).
I template dell'UI personalizzata sono elaborati come Jinja2.

### Sintassi base di Jinja2

```html
{# Commento #}
{{ nome_variabile }}
{% if condizione %} ... {% endif %}
{% for item in lista %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Struttura pagina

### Corrispondenza tra pagine e route

Il routing di Quart è fisso ed è auto-mappato ai seguenti nomi di template:

| Route | Template | Variabile template |
|--------|------------|----------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

La variabile `active` può essere usata per lo stato attivo della navigazione:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Struttura pagina consigliata

```html
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Navigazione (se diviso in template) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Contenuto pagina #}
  </main>

  {# Container notifiche toast #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Pattern suddivisione template

### Modularizzazione con include

L'UI di riferimento divide i template in parti piccole e le combina con `{% include %}`:

```
templates/
├── _nav.html              # Barra di navigazione comune
├── index.html             # Pagina principale (composta con include)
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

Anche l'UI personalizzata può usare lo stesso pattern:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Esempio barra di navigazione comune

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

## HTML puro (senza Jinja2)

È possibile costruire un'UI personalizzata usando HTML e JavaScript puri, senza usare le funzionalità di Jinja2.
Il file template viene servito come HTML così com'è:

```html
<!-- index.html senza sintassi Jinja2 -->
<!DOCTYPE html>
<html lang="it">
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

### Globali JavaScript disponibili

Anche senza Jinja2, le seguenti funzioni globali sono disponibili come base:

```javascript
window.tr(key)              // Traduzione i18n (window.tr("label.search") → "Search")
window.apiFetch(path, ...)  // Wrapper fetch con autenticazione
window.apiUrl(path)         // Costruisce URL base API
window.escapeHtml(str)      // Sanifica HTML
```

### Variabili template disponibili

Se usi Jinja2, queste variabili sono passate al template:

```html
{{ active }}        {# "search", "stats", "settings", ecc. #}
{{ lang }}          {# Lingua corrente ("it", "en", ecc.) #}
{{ version }}       {# Versione software #}
{{ api_version }}   {# Versione API #}
```

## Internazionalizzazione (i18n)

### Testo statico nei template

Per il testo statico nei template Jinja2, usa la sintassi `data-i18n`:

```html
<button data-i18n="label.search">Search</button>
<label data-i18n="label.query">Query</label>
```

Il testo non è tradotto sul server, ma il client applica la traduzione con `window.tr()`.

### Testo dinamico in JavaScript

Per il testo generato da JavaScript:

```javascript
const label = window.tr('label.search');  // Restituisce "Ricerca" in italiano
const msg = window.tr('msg.scan_complete', { count: 42 });
```

### Aggiunta di chiavi di traduzione

Le chiavi di traduzione vivono in `docs/i18n/` (non nel codice template).
Se aggiungi una nuova chiave, registrala in:

- `docs/i18n/it.json` (italiano)
- `docs/i18n/en.json` (inglese)
- Altre lingue secondo necessità

### Formato chiavi

Le chiavi seguono il pattern `namespace.key`:

```json
{
  "label": {
    "search": "Ricerca",
    "query": "Query"
  },
  "msg": {
    "scan_complete": "Scansione completata"
  }
}
```

## Validazione del form

### Attributi HTML5

Sfrutta gli attributi di validazione HTML5:

```html
<input type="email" required id="email" name="email">
<input type="number" min="1" max="100" id="rating" name="rating">
<input type="text" pattern="[a-z0-9]+" id="tag" name="tag">
```

### Validazione custom

Per validazione più complessa, usa JavaScript:

```javascript
function validateForm(formEl) {
  const values = new FormData(formEl);
  const errors = {};

  if (!values.get('query')) {
    errors.query = 'Query is required';
  }

  return Object.keys(errors).length === 0 ? null : errors;
}
```

## Accessibilità

### Struttura semantica

Usa sempre tag semantici:

```html
<header>...</header>
<main>...</main>
<nav>...</nav>
<article>...</article>
<aside>...</aside>
<footer>...</footer>
```

### ARIA labels

Per elementi non semantici, usa ARIA:

```html
<div role="button" aria-label="Close dialog" onclick="...">×</div>
<div id="search-results" role="region" aria-labelledby="search-title" aria-live="polite">
  ...
</div>
```

### Contrasto colore

Mantieni sempre il contrasto minimo WCAG AA (4.5:1 per il testo).

## Link e risorse

- [Jinja2 Docs](https://jinja.palletsprojects.com/templates/)
- [HTML Semantico](https://html.spec.whatwg.org/multipage/semantics.html)
- [WCAG 2.1](https://www.w3.org/WAI/WCAG21/quickref/)
