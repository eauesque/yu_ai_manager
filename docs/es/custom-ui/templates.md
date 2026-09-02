# Guía de plantillas — Plantillas Jinja2 y estructura de página

Guía de diseño de plantillas para interfaces personalizadas.

## Motor de plantillas

YU AI Manager utiliza el motor de plantillas [Jinja2](https://jinja.palletsprojects.com/).
Las plantillas de interfaz personalizada también se procesan como Jinja2.

### Sintaxis básica de Jinja2

```html
{# Comentario #}
{{ nombre_variable }}
{% if condición %} ... {% endif %}
{% for item in lista %} ... {% endfor %}
{% include "_parcial.html" %}
{% block contenido %}...{% endblock %}
```

## Estructura de página

### Correspondencia de página y ruta

El enrutamiento de Quart es fijo y se asigna automáticamente a los siguientes nombres de plantilla:

| Ruta | Plantilla | Variable de plantilla |
|------|-----------|------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

La variable `active` se puede usar para el estado activo de navegación:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Búsqueda</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Estadísticas</a>
</nav>
```

### Estructura de página recomendada

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Título de página - Mi interfaz personalizada</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Navegación (en caso de división de plantilla) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Contenido de página #}
  </main>

  {# Para notificación tipo toast #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Patrón de división de plantilla

### Componentización por include

La interfaz de referencia divide las plantillas en partes finas y las combina con `{% include %}`:

```
templates/
├── _nav.html              # Barra de navegación común
├── index.html             # Página principal (ensamblada por include)
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

Se puede usar el mismo patrón en interfaz personalizada:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Ejemplo de barra de navegación común

`templates/_nav.html`:

```html
<nav class="navbar">
  <a href="/" class="nav-brand">Mi interfaz</a>
  <div class="nav-links">
    <a href="/" class="nav-link{% if active == 'search' %} active{% endif %}">
      Búsqueda
    </a>
    <a href="/stats" class="nav-link{% if active == 'stats' %} active{% endif %}">
      Estadísticas
    </a>
    <a href="/tools" class="nav-link{% if active == 'tools' %} active{% endif %}">
      Herramientas
    </a>
    <a href="/settings" class="nav-link{% if active == 'settings' %} active{% endif %}">
      Configuración
    </a>
  </div>
  <button id="themeToggle" onclick="toggleDarkMode()">🌙</button>
</nav>
```

## HTML puro (sin Jinja2)

También es posible construir interfaz personalizada utilizando solo HTML + JavaScript puro, sin usar características de Jinja2.
Los archivos de plantilla se entregan como HTML tal cual:

```html
<!-- index.html sin sintaxis Jinja2 -->
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Interfaz SPA personalizada</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

En este caso, el enrutamiento se controla en el lado JavaScript y el servidor no devuelve
la misma `index.html` para todas las rutas.
Se requieren archivos de plantilla separados para cada ruta de página (`/stats`, `/tools`, etc.).

### Configuración similar a SPA

Si desea usar el mismo HTML para todas las páginas, incluya el HTML común desde cada plantilla:

```html
{# stats.html, tools.html, settings.html, etc. #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`:
```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Mi interfaz SPA</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div id="app" data-route="{{ active }}"></div>
  <script type="module" src="/static/app.js"></script>
</body>
</html>
```

El lado JavaScript lee `data-route` para cambiar de página.

## Internacionalización (i18n)

La interfaz de referencia soporta internacionalización mediante atributo `data-i18n`:

```html
<span data-i18n="nav.search">Búsqueda</span>
<input data-i18n-placeholder="search.placeholder" placeholder="Buscar por etiqueta...">
<button data-i18n-aria-label="nav.menu" aria-label="Menú">☰</button>
```

Si usa i18n en interfaz personalizada, puede utilizar el motor i18n incluido en
`nav.js` de la interfaz de referencia o implementar su propio sistema de traducción.

### Ejemplo de implementación simple de i18n

```javascript
const translations = {
  es: { 'search': 'Búsqueda', 'stats': 'Estadísticas', 'settings': 'Configuración' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['es'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## favicon

Para colocar favicon propio en interfaz personalizada, colóquelo en `static/`:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Las solicitudes a `/favicon.ico` se procesan en la ruta de Quart y
se redirigen a `static/favicon.svg` de la interfaz activa.

## Página de error

Si coloca plantilla `error.html`, se mostrará cuando ocurra error del servidor:

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Error</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  <main style="text-align: center; padding: 60px 20px;">
    <h1>Algo salió mal</h1>
    <p>Por favor, inténtelo más tarde.</p>
    <a href="/">Volver a inicio</a>
  </main>
</body>
</html>
```

## Lista de plantilla de interfaz predeterminada

Composición de plantilla de interfaz de referencia (referencia):

| Categoría | Número de archivos | Descripción |
|-----------|---|------|
| Página principal | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Componentes comunes | 2 | `_nav.html`, `_ext_nav.html` |
| División de index | 24 | Formulario de búsqueda, modal, control de cuadrícula, panel de regex, etc. |
| División de settings | 5 | Encabezado, grupo de pestañas, barra de guardado |
| División de tools | 14 | Herramientas de búsqueda/análisis, mantenimiento, configuración de escaneo |
| Otras páginas | 12 | stats, story, inspect, extensions, share, LAN share |
| **Total** | **66** | — |

La interfaz personalizada no necesita reimplementar todas estas.
Solo cree plantillas para las páginas que necesite; solo esas páginas se mostrarán personalizadas.
