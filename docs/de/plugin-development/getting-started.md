# Plugin-Entwicklungsleitfaden

Leitfaden zur Entwicklung von Plugins (Extensions) für YU AI Manager.

## Minimalaufbau

Ein Plugin funktioniert, sobald Sie unter `extensions/` einen Ordner anlegen und folgende zwei Dateien bereitstellen.

```
extensions/
  my-plugin/
    extension.json      # Manifest (erforderlich)
    my_plugin.py        # Entry Point (erforderlich)
```

### extension.json (minimal)

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

### my_plugin.py (minimal)

```python
"""My Plugin — 最小構成サンプル"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Extension ローダーが呼び出すエントリポイント。"""
    return bp
```

Indem Sie lediglich `get_blueprint()` exportieren, registriert das Extension-System den Blueprint automatisch.

## API-Routen hinzufügen

Sie können eigene API-Endpunkte über ein Plugin hinzufügen.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- Als URL-Präfix wird `/ext/<plugin-name>/` empfohlen (Kollisionsvermeidung)
- Wenn Sie in `extension.json` `"blueprint_prefix": "/ext/my-plugin"` setzen, wird automatisch ein Eintrag zur Navigation hinzugefügt

## Templates (UI-Seiten)

Plugins können eigene HTML-Seiten haben.

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

In Templates können Sie das bestehende `_nav.html` erweitern, um ein einheitliches Aussehen zu erreichen:

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

## Einstellungsschema (config_schema)

Damit Benutzer unter Settings > Extensions die Plugin-Einstellungen ändern können, definieren Sie `config_schema` in `extension.json`.

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

So lesen Sie die Werte auf Python-Seite:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Hooks

Extensions können an Hook-Punkten Verarbeitung einfügen.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Hook-Funktionen werden im Python-Modul definiert; der Extension Manager erkennt sie automatisch.

## Navigationseintrag hinzufügen

Wenn Sie das Feld `nav` in `extension.json` hinzufügen, wird ein Link automatisch in der Sidebar angezeigt.

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

## Veröffentlichung als Git-Repository

Wenn Sie das Plugin als Git-Repository veröffentlichen, kann es von Benutzern unter Settings > Extensions > Install per URL installiert werden.

### Repository-Struktur

```
my-plugin/
  extension.json     # Im Root platzieren
  my_plugin.py
  templates/
  README.md
```

### Installationsablauf

1. Benutzer gibt unter Settings > Extensions > Install eine Git-URL ein
2. System klont das Repository per `git clone --depth 1`
3. `extension.json` wird validiert
4. Dateien werden im Verzeichnis `extensions/` abgelegt
5. Serverneustart aktiviert das Plugin

### Marketplace-Registrierung

Wenn Sie in `config.json` die URL eines Index-JSONs unter `extension_index_url` setzen, können Sie Plugins aus dem Marketplace-Tab durchsuchen und installieren.

Format des Index-JSONs:

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

## CSS-Präfix-Konvention

Um Stilkonflikte zu vermeiden, verwenden Sie für CSS-Klassen ein plugin-spezifisches Präfix:

```css
.mp-container { ... }
.mp-card { ... }
```

## Sicherheitshinweise

- Fügen Sie Benutzereingaben nicht direkt in SQL ein (verwenden Sie `?`-Platzhalter)
- Achten Sie auf Path-Traversal-Angriffe
- Setzen Sie bei externen API-Aufrufen einen User-Agent
- CSRF-Header (`X-Requested-With`) werden vom globalen Interceptor automatisch injiziert
