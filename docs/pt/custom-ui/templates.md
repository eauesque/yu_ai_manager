# Guia de Templates — Templates Jinja2 e Estrutura de Páginas

Guia de design de templates para UIs personalizadas.

## Engine de Templates

O YU AI Manager usa o engine de templates [Jinja2](https://jinja.palletsprojects.com/).
Os templates de UIs personalizadas também são processados como Jinja2.

### Sintaxe Básica do Jinja2

```html
{# comentário #}
{{ nome_variavel }}
{% if condição %} ... {% endif %}
{% for item in lista %} ... {% endfor %}
{% include "_partial.html" %}
{% block content %}...{% endblock %}
```

## Estrutura de Páginas

### Correspondência entre Páginas e Rotas

O roteamento do Quart é fixo e mapeado automaticamente para os seguintes nomes de templates:

| Rota | Template | Variáveis de Template |
|--------|------------|----------------|
| `/` | `index.html` | `active="search"` |
| `/stats` | `stats.html` | `active="stats"` |
| `/tools` | `tools.html` | `active="tools"` |
| `/settings` | `settings.html` | `active="settings"` |
| `/extensions` | `extensions.html` | `active="extensions"` |
| `/story` | `story.html` | `active="story"` |
| `/inspect` | `inspect.html` | `active="inspect"` |

A variável `active` pode ser usada para o estado ativo da navegação:

```html
<nav>
  <a href="/" class="{% if active == 'search' %}active{% endif %}">Search</a>
  <a href="/stats" class="{% if active == 'stats' %}active{% endif %}">Stats</a>
</nav>
```

### Estrutura de Página Recomendada

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Title - My Custom UI</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="dark">
  {# Navegação (ao dividir templates) #}
  {% include "_nav.html" %}

  <main id="main-content">
    {# Conteúdo da página #}
  </main>

  {# Para notificações toast #}
  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <script src="/static/app.js"></script>
</body>
</html>
```

## Padrões de Divisão de Templates

### Modularização com include

A UI de referência divide os templates em partes menores e os combina com `{% include %}`:

```
templates/
├── _nav.html              # barra de navegação comum
├── index.html             # página principal (montada com includes)
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

Você pode usar o mesmo padrão em UIs personalizadas:

```html
{# index.html #}
{% include "_nav.html" %}
{% include "index/_search_form.html" %}
{% include "index/_results_grid.html" %}
```

### Exemplo de Barra de Navegação Comum

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
  <button id="themeToggle" onclick="toggleDarkMode()">&#127769;</button>
</nav>
```

## HTML Puro (sem Jinja2)

Você também pode construir uma UI personalizada apenas com HTML + JavaScript puro, sem usar os recursos do Jinja2.
Os arquivos de template são entregues como HTML normalmente:

```html
<!-- index.html sem sintaxe Jinja2 -->
<!DOCTYPE html>
<html lang="pt-BR">
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

Nesse caso, o roteamento é controlado pelo lado do JavaScript, mas o servidor
não retorna o mesmo `index.html` para todas as rotas de página.
Cada rota de página (`/stats`, `/tools`, etc.) requer seu próprio arquivo de template.

### Configuração Similar a SPA

Se você quiser usar o mesmo HTML para todas as páginas, faça include do HTML comum em cada template:

```html
{# stats.html, tools.html, settings.html, etc. #}
{% include "_spa_shell.html" %}
```

`_spa_shell.html`:
```html
<!DOCTYPE html>
<html lang="pt-BR">
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

No lado do JavaScript, leia `data-route` para alternar páginas.

## Internacionalização (i18n)

A UI de referência suporta internacionalização com o atributo `data-i18n`:

```html
<span data-i18n="nav.search">Pesquisar</span>
<input data-i18n-placeholder="search.placeholder" placeholder="Pesquisar por tags...">
<button data-i18n-aria-label="nav.menu" aria-label="Menu">&#9776;</button>
```

Para usar i18n em UIs personalizadas, você pode usar o engine i18n incluído no `nav.js` da UI de referência ou implementar seu próprio sistema de tradução.

### Exemplo Simples de Implementação i18n

```javascript
const translations = {
  pt: { 'search': 'Pesquisar', 'stats': 'Estatísticas', 'settings': 'Configurações' },
  en: { 'search': 'Search', 'stats': 'Stats', 'settings': 'Settings' },
};

function setLang(lang) {
  const dict = translations[lang] || translations['pt'];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) el.textContent = dict[key];
  });
  localStorage.setItem('lang', lang);
}
```

## Favicon

Para colocar um favicon personalizado na UI, posicione em `static/`:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

Requisições para `/favicon.ico` são processadas pela rota do Quart e
redirecionadas para `static/favicon.svg` da UI ativa.

## Página de Erro

Ao posicionar um template `error.html`, ele será exibido em erros do servidor:

```html
{# templates/error.html #}
<!DOCTYPE html>
<html lang="pt-BR">
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

## Lista de Templates da UI Padrão

Estrutura de templates da UI de referência (para referência):

| Categoria | Nº de Arquivos | Descrição |
|---------|----------|------|
| Páginas principais | 9 | index, stats, tools, settings, story, inspect, extensions, share, error |
| Partes comuns | 2 | `_nav.html`, `_ext_nav.html` |
| Divisão do index | 24 | formulário de pesquisa, modais, controle de grid, painel regex, etc. |
| Divisão de settings | 5 | cabeçalho, grupos de abas, barra de salvamento |
| Divisão de tools | 14 | ferramentas de pesquisa/análise, manutenção, configuração de varredura |
| Outras páginas | 12 | stats, story, inspect, extensions, share, LAN share |
| **Total** | **66** | — |

Você não precisa reimplementar todos eles em uma UI personalizada.
Se você criar apenas os templates necessários, somente essas páginas serão exibidas de forma personalizada.
