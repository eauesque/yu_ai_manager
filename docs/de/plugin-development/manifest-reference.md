# extension.json Manifest-Referenz

Eine Manifest-Datei, die Metadaten und Einstellungen einer Extension definiert. Sie wird unter `extensions/<name>/extension.json` abgelegt.

## Pflichtfelder

| Feld | Typ | Beschreibung |
|---|---|---|
| `name` | string | Eindeutiger Bezeichner der Extension. Muss mit dem Verzeichnisnamen übereinstimmen |
| `version` | string | Semantische Version (z. B. `"1.0.0"`) |
| `entry` | string | Dateiname des Python-Entry-Points (z. B. `"my_plugin.py"`) |

## Optionale Felder

| Feld | Typ | Standard | Beschreibung |
|---|---|---|---|
| `description` | string | `""` | Kurzbeschreibung (wird in UI-Cards angezeigt) |
| `author` | string | `""` | Name des Autors |
| `type` | string | `"general"` | Extension-Typ: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Array der verwendeten Hook-Punkt-Namen |
| `has_blueprint` | bool | `false` | true, wenn ein Flask Blueprint vorhanden ist |
| `blueprint_prefix` | string | `""` | URL-Präfix des Blueprints (z. B. `"/ext/my-plugin"`) |
| `nav` | object | `null` | Navigationseintrag-Konfiguration |
| `config` | object | `{}` | Grundkonfiguration |
| `config_schema` | object | `{}` | Schema für Benutzereinstellungen |

## Objekt `config`

| Feld | Typ | Standard | Beschreibung |
|---|---|---|---|
| `enabled` | bool | `true` | Initialer Aktivierungsstatus |
| `priority` | int | `500` | Ladereihenfolge (kleinere Werte werden zuerst geladen) |

## Objekt `nav`

| Feld | Typ | Beschreibung |
|---|---|---|
| `label` | string | Anzeigelabel in der Navigation |
| `icon` | string | Emoji-Icon (z. B. `"🔌"`) |

Wenn `nav` gesetzt ist, sollten auch `has_blueprint: true` und `blueprint_prefix` gesetzt sein.

## Objekt `config_schema`

Definiert Einstellungen, die Benutzer über die Settings-UI ändern können. Jeder Schlüssel wird zu einem Einstellungsfeld.

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

### Felddefinition

| Eigenschaft | Typ | Beschreibung |
|---|---|---|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Standardwert |
| `label` | string | Anzeigename in der UI (bei Weglassen wird der Schlüsselname verwendet) |
| `description` | string | Hilfetext |

### Lesen und Schreiben von Einstellungswerten

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# Lesen
val = get_extension_config_value("my-plugin", "field_name", "default")

# Schreiben
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API:
```
GET  /api/extensions/<name>/config    — Schema und aktuelle Werte abrufen
POST /api/extensions/<name>/config    — Speichern mit {"values": {"key": "val"}}
```

## Vollständiges Beispiel

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
