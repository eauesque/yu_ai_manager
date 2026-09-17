# Guide de Développement de Plugins

Guide pour développer des plugins (Extensions) pour YU AI Manager.

## Configuration Minimale

Un plugin s'obtient en créant un dossier dans `extensions/` et en préparant les 2 fichiers suivants.

```
extensions/
  my-plugin/
    extension.json      # Manifeste (obligatoire)
    my_plugin.py        # Point d'entrée (obligatoire)
```

### extension.json (minimum)

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

### my_plugin.py (minimum)

```python
"""My Plugin — Sample minimum configuration"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Entry point called by the Extension loader."""
    return bp
```

Il suffit d'exposer `get_blueprint()` pour que le système d'Extensions enregistre automatiquement le blueprint.

## Ajout de Routes API

Vous pouvez ajouter vos propres endpoints API depuis un plugin.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- Le préfixe d'URL `/ext/<plugin-name>/` est recommandé (évite les collisions)
- Définir `"blueprint_prefix": "/ext/my-plugin"` dans `extension.json` ajoute automatiquement à la navigation

## Templates (pages UI)

Un plugin peut avoir ses propres pages HTML.

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

Les templates peuvent étendre `_nav.html` existant pour un rendu uniforme :

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

## Schéma de Configuration (config_schema)

Pour permettre à l'utilisateur de modifier les paramètres du plugin depuis Settings > Extensions, définir `config_schema` dans `extension.json`.

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

Pour lire les valeurs de configuration côté Python :

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Hooks

Les Extensions peuvent injecter du traitement aux points de hook.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Définir les fonctions de hook dans le module Python, détectées automatiquement par l'Extension Manager.

## Ajout à la Navigation

En ajoutant le champ `nav` dans `extension.json`, un lien est automatiquement ajouté à la barre latérale.

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

## Publication via Dépôt Git

En publiant le plugin comme dépôt Git, les utilisateurs peuvent l'installer depuis Settings > Extensions > onglet Install en saisissant l'URL.

### Structure du Dépôt

```
my-plugin/
  extension.json     # Placé à la racine
  my_plugin.py
  templates/
  README.md
```

### Flux d'Installation

1. L'utilisateur saisit l'URL Git dans Settings > Extensions > Install
2. Le système clone le dépôt avec `git clone --depth 1`
3. Validation de `extension.json`
4. Placement dans le répertoire `extensions/`
5. Activation au redémarrage du serveur

### Enregistrement au Marketplace

En configurant l'URL d'un JSON d'index dans `extension_index_url` de `config.json`, on peut parcourir et installer depuis l'onglet marketplace.

Format du JSON d'index :

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

## Convention de Préfixe CSS

Pour éviter les collisions de styles, utilisez un préfixe spécifique au plugin pour les classes CSS :

```css
.mp-container { ... }
.mp-card { ... }
```

## Notes de Sécurité

- Ne pas intégrer directement les entrées utilisateur dans SQL (utiliser les placeholders `?`)
- Attention aux attaques par traversée de chemin
- Définir User-Agent lors d'appels à des API externes
- L'en-tête CSRF (`X-Requested-With`) est injecté automatiquement par l'intercepteur global existant
