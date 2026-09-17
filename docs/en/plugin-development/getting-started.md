# Plugin Development Guide

This guide explains how to develop plugins (Extensions) for YU AI Manager.

## Minimal Setup

A plugin works with just two files placed in a folder under the `extensions/` directory.

```
extensions/
  my-plugin/
    extension.json      # Manifest (required)
    my_plugin.py        # Entry point (required)
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
"""My Plugin — minimal example"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Entry point called by the Extension loader."""
    return bp
```

The Extension system automatically registers the blueprint as long as the module exposes `get_blueprint()`.

## Adding API Routes

A plugin can add its own API endpoints.

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- It is recommended to use `/ext/<plugin-name>/` as the URL prefix to avoid collisions.
- The link appears in navigation automatically if you set `"blueprint_prefix": "/ext/my-plugin"` in `extension.json`.

## Templates (UI Pages)

A plugin can include its own HTML pages.

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

Templates can extend the existing `_nav.html` to maintain a consistent look:

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

## Configuration Schema (config_schema)

Users can modify plugin settings from Settings > Extensions by defining `config_schema` in `extension.json`.

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

To read configuration values from Python:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Hooks

Extensions can hook into specific processing points.

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

The Extension Manager automatically discovers hook functions defined in the Python module.

## Adding Navigation Links

The sidebar displays a link automatically if you add a `nav` field to `extension.json`.

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

## Publishing via Git Repository

Users can install a plugin by entering its URL in Settings > Extensions > Install if the plugin is published as a Git repository.

### Repository Structure

```
my-plugin/
  extension.json     # Place at root
  my_plugin.py
  templates/
  README.md
```

### Installation Flow

1. The user enters a Git URL in Settings > Extensions > Install.
2. The system clones the repository with `git clone --depth 1`.
3. It validates `extension.json`.
4. It places the plugin under the `extensions/` directory.
5. A server restart activates the plugin.

### Marketplace Registration

Users can browse and install plugins from the Marketplace tab by setting the URL of an index JSON in `extension_index_url` within `config.json`.

Index JSON format:

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

## CSS Prefix Convention

Use a plugin-specific prefix for CSS classes to prevent style collisions:

```css
.mp-container { ... }
.mp-card { ... }
```

## Security Notes

- Never embed user input directly in SQL; use `?` placeholders instead.
- Guard against path traversal attacks on file paths.
- Set a User-Agent header for external API calls.
- The existing global interceptor automatically injects the CSRF header (`X-Requested-With`).
