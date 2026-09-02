# Guia de Desenvolvimento de UI Personalizada

Um guia para o sistema de UI personalizada que permite substituir completamente o frontend do YU AI Manager.

## Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Começar](quickstart.md) — Instruções para criar uma UI com configuração mínima
- [Guia de Design](design-guide.md) — Design CSS, temas, responsividade e componentes
- [Guia de Templates](templates.md) — Padrões Jinja2, i18n e estrutura de página
- [Recursos Avançados](advanced.md) — Atualizações SSE em tempo real, operações em lote e segurança
- [Referência de API](api-reference.md) — Coleção de links para toda a documentação de API

## Visão Geral

YU AI Manager possui uma API de backend completamente separada, permitindo que você substitua livremente o frontend. Uma UI personalizada é ativada simplesmente colocando-a no diretório `ui/<nome>/`.

### O que é Possível com Este Sistema

- **Substituição Completa de UI**: Personalize todas as páginas — tela de busca, dashboard de estatísticas, configurações, etc.
- **Personalização de Tema**: Mude o esquema de cores apenas sobrescrevendo variáveis CSS
- **Substituição Parcial**: Personalize apenas as páginas necessárias e use a UI padrão para o resto
- **Geração de UI por IA**: Passe a documentação de API para Claude ou ChatGPT para gerar UI automaticamente

### Arquitetura

```
yu_ai_manager/
├── ui/
│   ├── default/              # UI de Referência (built-in)
│   │   ├── manifest.json     # Metadados de UI (obrigatório)
│   │   ├── templates/        # Templates HTML Jinja2
│   │   │   ├── index.html    # Página principal de busca
│   │   │   ├── stats.html    # Dashboard de estatísticas
│   │   │   ├── tools.html    # Página de ferramentas
│   │   │   ├── settings.html # Página de configurações
│   │   │   ├── story.html    # Página Your Story
│   │   │   ├── inspect.html  # Inspetor de metadados
│   │   │   └── _nav.html     # Barra de navegação comum (include)
│   │   └── static/           # CSS, JS, imagens
│   │       ├── css/          # Folhas de estilo
│   │       ├── dist/         # Saída de build TypeScript
│   │       └── favicon.svg   # Ícone de favorito
│   ├── custom/               # UI personalizada (gitignored, detectada automaticamente)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # UI adicional (nome livre)
│       ├── manifest.json
│       └── ...
├── routes/                   # Rotas de API do servidor
│   ├── pages.py              # Definições de roteamento de página
│   └── ...                   # Vários endpoints de API
└── docs/api/                 # Documentação de API
```

### Ordem de Resolução de UI

Ao iniciar o servidor, a UI a ser usada é determinada pela seguinte prioridade:

| Prioridade | Condição | Comportamento |
|-----------|----------|--------------|
| 1 | `"ui": "my-theme"` definido em `config.json` | Usa `ui/my-theme/` conforme especificado |
| 2 | Existe um `manifest.json` válido em `ui/custom/` | Detecta e usa `ui/custom/` automaticamente |
| 3 | Nenhuma das opções acima | Usa `ui/default/` como fallback |

### manifest.json

Todas as UI personalizadas devem ter um `manifest.json` obrigatório:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| Campo | Obrigatório | Descrição |
|-------|-----------|-----------|
| `name` | Sim | Nome de identificação da UI (recomenda-se corresponder ao nome do diretório) |
| `version` | Sim | Versionamento semântico |
| `description` | Não | Descrição da UI |
| `author` | Não | Nome do autor |
| `api_version` | Não | Versão de API suportada (`"1"`) |
| `type` | Não | `"full"` (padrão) ou `"theme"` |

### Entrega de Arquivos Estáticos

O diretório `static/` da UI personalizada é mapeado para a URL `/static/` do Flask:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

Referência de HTML:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### API de Gerenciamento de UI

A UI pode ser gerenciada através da aba "UI" da página de Configurações ou via API:

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/api/ui/list` | Lista de UI instaladas |
| POST | `/api/ui/switch` | Alterna UI ativa (requer reinicialização) |
| POST | `/api/ui/install` | Instala UI de URL (apenas localhost) |
| DELETE | `/api/ui/<name>/uninstall` | Desinstala UI (apenas localhost) |

### Ferramentas MCP

A UI também pode ser gerenciada via MCP (Model Context Protocol):

- `list_uis()` — Lista de UI instaladas
- `switch_ui(name)` — Alterna UI ativa
- `install_ui(url)` — Instala UI de URL
- `uninstall_ui(name)` — Desinstala UI

