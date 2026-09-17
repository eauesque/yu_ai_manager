# Guía de desarrollo de complementos

Guía para desarrollar complementos (Extension) para YU AI Manager.

## Configuración mínima

Complemento se crea en carpeta bajo directorio `extensions/`, requiere solo 2 archivos:

```
extensions/
  mi-plugin/
    extension.json      # Manifiesto (obligatorio)
    mi_plugin.py        # Punto de entrada (obligatorio)
```

### extension.json (mínimo)

```json
{
  "name": "mi-plugin",
  "version": "1.0.0",
  "description": "Mi primer complemento",
  "entry": "mi_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  }
}
```

### mi_plugin.py (mínimo)

```python
"""Mi complemento — Muestra configuración mínima"""

from quart import Blueprint

bp = Blueprint("mi_plugin", __name__)

def get_blueprint():
    """Punto entrada llamado cargador Extension."""
    return bp
```

Exponer `get_blueprint()` es suficiente, sistema Extension registra automáticamente blueprint.

## Agregar rutas API

Agregar endpoints API propios desde complemento:

```python
from quart import Blueprint, jsonify

bp = Blueprint("mi_plugin", __name__)

@bp.route("/ext/mi-plugin/api/hola")
def api_hola():
    return jsonify({"mensaje": "¡Hola de mi-plugin!"})

def get_blueprint():
    return bp
```

- Prefijo URL recomendado `/ext/<nombre-plugin>/` (previene colisiones)
- Configurar `"blueprint_prefix": "/ext/mi-plugin"` en `extension.json` para agregar automáticamente navegación

## Plantillas (páginas UI)

Complemento puede tener páginas HTML propias:

```
extensions/
  mi-plugin/
    extension.json
    mi_plugin.py
    templates/
      mi_plugin/
        index.html
```

```python
from quart import Blueprint, render_template

bp = Blueprint(
    "mi_plugin",
    __name__,
    template_folder="templates",
)

@bp.route("/ext/mi-plugin/")
def index():
    return render_template("mi_plugin/index.html")

def get_blueprint():
    return bp
```

Plantillas pueden extender `_nav.html` para apariencia uniforme:

```html
{% extends "_nav.html" %}
{% block title %}Mi complemento{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>Mi complemento</h1>
  <p>Tu contenido aquí.</p>
</div>
{% endblock %}
```

## Esquema configuración (config_schema)

Permitir usuarios cambiar configuración complemento en Configuración > Extensiones, definir `config_schema` en `extension.json`:

```json
{
  "name": "mi-plugin",
  "version": "1.0.0",
  "description": "Complemento configurable",
  "entry": "mi_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  },
  "config_schema": {
    "greeting": { "type": "string", "default": "Hola" },
    "max_items": { "type": "number", "default": 10 },
    "verbose": { "type": "boolean", "default": false }
  }
}
```

Leer valores configuración en Python:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("mi-plugin", "greeting", "Hola")
```

## Ganchos

Extension puede enlazar procesamiento en puntos gancho:

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```
