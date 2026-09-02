# Riferimento Manifesto extension.json

File manifesto che definisce le metainformazioni e le impostazioni dell'Extension. Posizionarlo in `extensions/<name>/extension.json`.

## Campi Obbligatori

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `name` | string | Identificatore unico dell'Extension. Deve corrispondere al nome directory |
| `version` | string | Versione semantica (es. `"1.0.0"`) |
| `entry` | string | Nome file entry point Python (es. `"my_plugin.py"`) |

## Campi Opzionali

| Campo | Tipo | Default | Descrizione |
|-------|------|---------|-------------|
| `description` | string | `""` | Breve descrizione (usata nella visualizzazione card UI) |
| `author` | string | `""` | Nome autore |
| `type` | string | `"general"` | Tipo Extension: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Array dei nomi dei punti hook usati |
| `has_blueprint` | bool | `false` | true se ha un Flask Blueprint |
| `blueprint_prefix` | string | `""` | Prefisso URL Blueprint (es. `"/ext/my-plugin"`) |
| `nav` | object | `null` | Configurazione link navigazione |
| `config` | object | `{}` | Configurazione base |
| `config_schema` | object | `{}` | Schema configurazione utente |

## Oggetto `config`

| Campo | Tipo | Default | Descrizione |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Stato abilitazione iniziale |
| `priority` | int | `500` | Ordine di caricamento (valori più piccoli vengono caricati prima) |

## Oggetto `nav`

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `label` | string | Etichetta da visualizzare nella navigazione |
| `icon` | string | Icona emoji (es. `"🔌"`) |

Se si imposta `nav`, impostare anche `has_blueprint: true` e `blueprint_prefix`.

## Oggetto `config_schema`

Definisce le impostazioni modificabili dagli utenti dall'UI Settings. Ogni chiave diventa un campo di impostazione.

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

### Definizione Campi

| Proprietà | Tipo | Descrizione |
|-----------|------|-------------|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Valore predefinito |
| `label` | string | Nome visualizzato nell'UI (se omesso usa il nome della chiave) |
| `description` | string | Testo di aiuto |

### Lettura/Scrittura Valori Configurazione

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# Lettura
val = get_extension_config_value("my-plugin", "field_name", "default")

# Scrittura
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API:
```
GET  /api/extensions/<name>/config    — Recupera schema e valore corrente
POST /api/extensions/<name>/config    — Salva con {"values": {"key": "val"}}
```

## Esempio Completo

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
