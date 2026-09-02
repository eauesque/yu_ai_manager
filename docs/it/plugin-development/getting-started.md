# Guida allo Sviluppo Plugin

Guida per sviluppare plugin (Extension) per YU AI Manager.

## Configurazione Minimale

Un plugin funziona semplicemente creando una cartella nella directory `extensions/` e preparando i seguenti 2 file.

```
extensions/
  my-plugin/
    extension.json      # Manifesto (obbligatorio)
    my_plugin.py        # Entry point (obbligatorio)
```

### extension.json (minimo)

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

### my_plugin.py (minimo)

```python
"""My Plugin — esempio configurazione minimale"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Entry point chiamato dal loader Extension."""
    return bp
```

Esporre solo `get_blueprint()` è sufficiente perché il sistema Extension registri automaticamente il blueprint.

## Aggiunta Route API

È possibile aggiungere endpoint API personalizzati dal plugin.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- Il prefisso URL consigliato è `/ext/<plugin-name>/` (prevenzione conflitti)
- Impostando `"blueprint_prefix": "/ext/my-plugin"` in `extension.json`, viene aggiunto automaticamente alla navigazione

## Template (Pagina UI)

I plugin possono avere le proprie pagine HTML.

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

Nei template è possibile estendere il `_nav.html` esistente per un'aspetto uniforme:

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

## Schema di Configurazione (config_schema)

Per permettere agli utenti di modificare le impostazioni del plugin da Settings > Extensions, definire `config_schema` in `extension.json`.

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

Per leggere i valori di configurazione lato Python:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Hook

Le Extension possono inserire elaborazioni nei punti di hook.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Le funzioni hook vengono definite all'interno del modulo Python e vengono rilevate automaticamente dall'Extension Manager.

## Aggiunta Navigazione

Aggiungendo il campo `nav` in `extension.json`, viene aggiunto automaticamente un link alla sidebar.

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

## Pubblicazione in Repository Git

Pubblicando il plugin come repository Git, gli utenti possono installarlo inserendo l'URL dalla scheda Install in Settings > Extensions.

### Struttura Repository

```
my-plugin/
  extension.json     # Posizionare nella radice
  my_plugin.py
  templates/
  README.md
```

### Flusso di Installazione

1. L'utente inserisce l'URL Git nella scheda Install di Settings > Extensions
2. Il sistema clona il repository con `git clone --depth 1`
3. Valida `extension.json`
4. Posiziona nella directory `extensions/`
5. Abilitato al riavvio del server

### Registrazione nel Marketplace

Impostando l'URL del JSON indice in `extension_index_url` di `config.json`, è possibile navigare e installare dalla scheda Marketplace.

Formato JSON indice:

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

## Convenzioni Prefisso CSS

Per prevenire conflitti di stile, usare prefissi specifici del plugin per le classi CSS:

```css
.mp-container { ... }
.mp-card { ... }
```

## Note sulla Sicurezza

- Non incorporare direttamente l'input utente in SQL (usare segnaposto `?`)
- Attenzione agli attacchi di path traversal sui percorsi file
- Impostare User-Agent nelle chiamate API esterne
- L'header CSRF (`X-Requested-With`) viene iniettato automaticamente dall'interceptor globale esistente
