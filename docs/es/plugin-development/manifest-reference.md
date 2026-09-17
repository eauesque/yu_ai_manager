# Referencia de manifiesto extension.json

Archivo manifiesto define metainformación y configuración Extension. Se coloca en `extensions/<nombre>/extension.json`.

## Campos obligatorios

| Campo | Tipo | Descripción |
|-------|------|------|
| `name` | string | Nombre identificación único Extension. Debe coincidir nombre directorio |
| `version` | string | Versionado semántico (ejemplo: `"1.0.0"`) |
| `entry` | string | Nombre archivo punto entrada Python (ejemplo: `"mi_plugin.py"`) |

## Campos opcionales

| Campo | Tipo | Predeterminado | Descripción |
|-------|------|---|---|
| `description` | string | `""` | Texto descripción corta (usado pantalla tarjeta UI) |
| `author` | string | `""` | Nombre autor |
| `type` | string | `"general"` | Tipo Extension: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Array nombres puntos gancho usado |
| `has_blueprint` | bool | `false` | true si posee Flask Blueprint |
| `blueprint_prefix` | string | `""` | Prefijo URL Blueprint (ejemplo: `"/ext/mi-plugin"`) |
| `nav` | object | `null` | Configuración enlace navegación |
| `config` | object | `{}` | Configuración base |
| `config_schema` | object | `{}` | Esquema configuración usuario |

## Objeto `config`

| Campo | Tipo | Predeterminado | Descripción |
|-------|------|---|---|
| `enabled` | bool | `true` | Estado habilitado inicial |
| `priority` | int | `500` | Orden carga (valor menor carga primero) |

## Objeto `nav`

| Campo | Tipo | Descripción |
|-------|------|------|
| `label` | string | Etiqueta mostrada navegación |
| `icon` | string | Icono emoji (ejemplo: `"🔌"`) |

Si configura `nav`, también configurar `has_blueprint: true` y `blueprint_prefix`.

## Objeto `config_schema`

Define configuración modificable usuarios desde UI Configuración. Cada clave se convierte campo configuración:

```json
{
  "config_schema": {
    "nombre_campo": {
      "type": "string",
      "default": "valor",
      "label": "Nombre pantalla",
      "description": "Texto ayuda este campo"
    }
  }
}
```

### Definición campo

| Propiedad | Tipo | Descripción |
|-----------|------|------|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Valor predeterminado |
| `label` | string | Nombre mostrado UI (si omitido usar nombre clave) |
| `description` | string | Texto ayuda |

### Leer/escribir valores configuración

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# Leer
val = get_extension_config_value("mi-plugin", "nombre_campo", "predeterminado")

# Escribir
save_extension_config_values("mi-plugin", {"nombre_campo": "valor_nuevo"})
```

API:
```
GET  /api/extensions/<nombre>/config    — Obtener esquema y valores actuales
POST /api/extensions/<nombre>/config    — Guardar {"values": {"clave": "val"}}
```

## Ejemplo completo

```json
{
  "name": "mi-complemento-increible",
  "version": "1.2.0",
  "description": "Complemento increíble que hace cosas increíbles",
  "author": "Tu nombre",
  "type": "ui_widget",
  "entry": "awesome_plugin.py",
  "hooks": ["after_scan"],
  "has_blueprint": true,
  "blueprint_prefix": "/ext/awesome",
  "nav": {
    "label": "Increíble",
    "icon": "✨"
  },
  "config": {
    "enabled": true,
    "priority": 400
  },
  "config_schema": {
    "api_url": {
      "type": "string",
      "default": "",
      "label": "URL API",
      "description": "URL endpoint API externa"
    },
    "max_results": {
      "type": "integer",
      "default": 20,
      "label": "Resultados máximos",
      "description": "Número máximo resultados mostrados"
    },
    "auto_refresh": {
      "type": "boolean",
      "default": true,
      "label": "Actualización automática",
      "description": "Actualizar automáticamente datos al cargar página"
    }
  }
}
```
