# Guide des templates — Jinja2 et structure des pages

Guide de conception des templates pour l'UI personnalisée.

## Moteur de templates

YU AI Manager utilise le moteur de templates [Jinja2](https://jinja.palletsprojects.com/).
Les templates de l'UI personnalisée sont également traités comme Jinja2.

### Syntaxe de base Jinja2

```html
{# Commentaire #}
{{ variable }}
{% if condition %} ... {% endif %}
{% for item in list %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Structure des pages

### Correspondance pages et routes

Le routage Quart est fixe et mappe automatiquement vers les noms de templates suivants :

| Route | Template | Variables de template |
|--------|------------|----------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

La variable `active` peut être utilisée pour l'état actif de la navigation :

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Structure de page recommandée

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Navigation (si split en templates) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Contenu de la page #}
  </main>

  {# Pour les notifications toast #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Pattern de découpage des templates

### Modularisation avec include

L'UI de référence découpe les templates finement et les assemble avec `{% include %}` :

```
templates/
├── _nav.html              # Barre de navigation commune
├── index.html             # Page principale (assemblée avec include)
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

Le même pattern peut être utilisé dans l'UI personnalisée :

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Exemple de barre de navigation commune

`templates/_nav.html` :

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

## HTML pur (sans Jinja2)

Il est également possible de construire une UI personnalisée avec du HTML pur + JavaScript sans utiliser les fonctionnalités Jinja2.
Les fichiers de template sont distribués directement comme HTML :

```html
<!-- index.html sans syntaxe Jinja2 -->
<!DOCTYPE html>
<html lang="fr">
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

Dans ce cas, le routage est contrôlé côté JavaScript, mais le serveur ne peut pas retourner le même `index.html` pour toutes les routes.
Chaque route de page (`/stats`, `/tools`, etc.) nécessite son propre fichier template.

### Configuration de type SPA

Pour utiliser le même HTML pour toutes les pages, incluez du HTML commun depuis chaque template :

```html
{# stats.html, tools.html, settings.html, etc. #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html` :
```html
<!DOCTYPE html>
<html lang="fr">
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

Côté JavaScript, lire `data-route` pour changer de page.

## Internationalisation (i18n)

L'UI de référence prend en charge l'internationalisation via l'attribut `data-i18n` :

```html
<span data-i18n="nav.search">Recherche</span>
<input data-i18n-placeholder="search.placeholder" placeholder="Rechercher par tags...">
<button data-i18n-aria-label="nav.menu" aria-label="Menu">☰</button>
```

Pour utiliser i18n dans une UI personnalisée, utilisez le moteur i18n de `nav.js` de l'UI de référence ou implémentez votre propre système de traduction.

### Exemple d'implémentation i18n simple

```javascript
const translations = {
  fr: { 'search': 'Recherche', 'stats': 'Statistiques', 'settings': 'Paramètres' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['fr'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## Favicon

Pour placer un favicon personnalisé dans votre UI, placez-le dans `static/` :

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Les requêtes vers `/favicon.ico` sont traitées par la route Quart et redirigées vers `static/favicon.svg` de l'UI active.

## Pages d'erreur

Placer un template `error.html` l'affichera lors d'erreurs serveur :

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="fr">
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

## Liste des templates de l'UI par défaut

Structure des templates de l'UI de référence (pour référence) :

| Catégorie | Nombre de fichiers | Description |
|---------|----------|------|
| Pages principales | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Composants communs | 2 | `_nav.html`, `_ext_nav.html` |
| Découpage index | 24 | Formulaire de recherche, modales, contrôle de grille, panneau regex, etc. |
| Découpage settings | 5 | En-tête, groupes d'onglets, barre de sauvegarde |
| Découpage tools | 14 | Outils de recherche/analyse, maintenance, paramètres de scan |
| Autres pages | 12 | stats, story, inspect, extensions, share, LAN share |
| **Total** | **66** | — |

L'UI personnalisée n'a pas besoin de réimplémenter tous ces templates.
Il suffit de créer les templates pour les pages souhaitées.
