# Guia de Desenvolvimento de Plugins

Guia para desenvolver plugins (Extensions) para o YU AI Manager.

## Estrutura mínima

Um plugin funciona apenas com uma pasta dentro de `extensions/` e os 2 arquivos abaixo.

```
extensions/
  my-plugin/
    extension.json      # manifest (obrigatório)
    my_plugin.py        # entry point (obrigatório)
```

### extension.json (mínimo)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My first plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  }
}
```

### my_plugin.py (mínimo)

```python
"""My Plugin — minimal example"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Entry point called by the Extension loader."""
    return bp
```

Bastando expor `get_blueprint()`, o sistema de Extensions registra automaticamente o blueprint.

## Adicionando rotas de API

A partir do plugin é possível adicionar endpoints próprios de API.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- Recomenda-se o prefixo de URL `/ext/<plugin-name>/` (para evitar colisões)
- Definindo `"blueprint_prefix": "/ext/my-plugin"` no `extension.json`, ele é adicionado automaticamente à navegação

## Templates (páginas da UI)

Plugins podem ter suas próprias páginas HTML.

```
extensions/
  my-plugin/
    extension.json
    my_plugin.py
    templates/
      my_plugin/
        index.html
```

```python
from quart import Blueprint, render_template

bp = Blueprint(
    "my_plugin",
    __name__,
    template_folder="templates",
)

@bp.route("/ext/my-plugin/")
def index():
    return render_template("my_plugin/index.html")

def get_blueprint():
    return bp
```

Nos templates, é possível estender o `_nav.html` existente para manter uma aparência consistente:

```html
{% extends "_nav.html" %}
{% block title %}My Plugin{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>My Plugin</h1>
  <p>Your content here.</p>
</div>
{% endblock %}
```

## Schema de configuração (config_schema)

Para que o usuário possa alterar as configurações do plugin em Settings > Extensions, defina `config_schema` em `extension.json`.

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Configurable plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  },
  "config_schema": {
    "greeting": { "type": "string", "default": "Hello" },
    "max_items": { "type": "number", "default": 10 },
    "verbose": { "type": "boolean", "default": false }
  }
}
```

Para ler os valores no lado Python:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Hooks

Extensions podem injetar processamento em hook points.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

As funções de hook são definidas no módulo Python e detectadas automaticamente pelo Extension Manager.

## Adicionar à navegação

Adicionando o campo `nav` no `extension.json`, um link é adicionado automaticamente à sidebar.

```json
{
  "nav": {
    "label": "My Plugin",
    "icon": "🔌"
  },
  "has_blueprint": true,
  "blueprint_prefix": "/ext/my-plugin"
}
```

## Publicação como repositório Git

Publicando o plugin como um repositório Git, o usuário pode instalá-lo informando a URL em Settings > Extensions > Install.

### Estrutura do repositório

```
my-plugin/
  extension.json     # colocar na raiz
  my_plugin.py
  templates/
  README.md
```

### Fluxo de instalação

1. O usuário informa a URL Git em Settings > Extensions > Install
2. O sistema clona o repositório com `git clone --depth 1`
3. Valida o `extension.json`
4. Coloca em `extensions/`
5. Ativa ao reiniciar o servidor

### Registro no marketplace

Ao definir a URL do JSON de índice em `extension_index_url` no `config.json`, é possível navegar e instalar pela aba Marketplace.

Formato do JSON de índice:

```json
[
  {
    "name": "my-plugin",
    "description": "A useful plugin",
    "author": "Your Name",
    "version": "1.0.0",
    "url": "https://github.com/user/my-plugin.git"
  }
]
```

## Convenção de prefixo CSS

Para evitar colisão de estilos, use um prefixo específico do plugin em suas classes CSS:

```css
.mp-container { ... }
.mp-card { ... }
```

## Observações de segurança

- Não embuta entrada de usuário diretamente em SQL (use placeholders `?`)
- Atenção a ataques de traversal em paths
- Ao chamar APIs externas, configure User-Agent
- O cabeçalho CSRF (`X-Requested-With`) é injetado automaticamente pelo interceptor global existente
