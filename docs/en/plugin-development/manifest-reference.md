# extension.json Manifest Reference

This manifest file defines Extension metadata and configuration. Place it at `extensions/<name>/extension.json`.

## Required Fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique identifier for the Extension. It should match the directory name |
| `version` | string | Semantic version (e.g., `"1.0.0"`) |
| `entry` | string | Python entry point filename (e.g., `"my_plugin.py"`) |

## Optional Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `description` | string | `""` | Short description (displayed on UI cards) |
| `author` | string | `""` | Author name |
| `type` | string | `"general"` | Extension type: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Array of hook point names to use |
| `has_blueprint` | bool | `false` | Set to true if the Extension has a Flask Blueprint |
| `blueprint_prefix` | string | `""` | URL prefix for the Blueprint (e.g., `"/ext/my-plugin"`) |
| `nav` | object | `null` | Navigation link configuration |
| `config` | object | `{}` | Basic configuration |
| `config_schema` | object | `{}` | User-facing configuration schema |

## `config` Object

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Initial enabled state |
| `priority` | int | `500` | Load order (lower values load first) |

## `nav` Object

| Field | Type | Description |
|---|---|---|
| `label` | string | Label displayed in navigation |
| `icon` | string | Emoji icon (e.g., `"🔌"`) |

You should also set `has_blueprint: true` and `blueprint_prefix` if you configure `nav`.

## `config_schema` Object

This defines user-editable settings accessible from the Settings UI. Each key becomes a configuration field.

```json
{
  "config_schema": {
    "field_name": {
      "type": "string",
      "default": "value",
      "label": "Display Name",
      "description": "Help text for this field"
    }
  }
}
```

### Field Definition

| Property | Type | Description |
|---|---|---|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Default value |
| `label` | string | Display name in the UI (falls back to the key name if omitted) |
| `description` | string | Help text |

### Reading and Writing Configuration Values

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# Read
val = get_extension_config_value("my-plugin", "field_name", "default")

# Write
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API:
```
GET  /api/extensions/<name>/config    — Retrieve schema and current values
POST /api/extensions/<name>/config    — Save with {"values": {"key": "val"}}
```

## Full Example

```json
{
  "name": "my-awesome-plugin",
  "version": "1.2.0",
  "description": "An awesome plugin that does amazing things",
  "author": "Your Name",
  "type": "ui_widget",
  "entry": "awesome_plugin.py",
  "hooks": ["after_scan"],
  "has_blueprint": true,
  "blueprint_prefix": "/ext/awesome",
  "nav": {
    "label": "Awesome",
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
      "label": "API URL",
      "description": "External API endpoint URL"
    },
    "max_results": {
      "type": "integer",
      "default": 20,
      "label": "Max Results",
      "description": "Maximum number of results to display"
    },
    "auto_refresh": {
      "type": "boolean",
      "default": true,
      "label": "Auto Refresh",
      "description": "Automatically refresh data on page load"
    }
  }
}
```
