# Référence du Manifeste extension.json

Fichier manifeste définissant les méta-informations et la configuration d'une Extension. Placé dans `extensions/<name>/extension.json`.

## Champs Obligatoires

| Champ | Type | Description |
|---|---|---|
| `name` | string | Nom d'identification unique de l'Extension. Doit correspondre au nom du répertoire |
| `version` | string | Version sémantique (ex : `"1.0.0"`) |
| `entry` | string | Nom du fichier de point d'entrée Python (ex : `"my_plugin.py"`) |

## Champs Optionnels

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `description` | string | `""` | Description courte (utilisée dans l'affichage carte UI) |
| `author` | string | `""` | Nom de l'auteur |
| `type` | string | `"general"` | Type d'Extension : `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Tableau des noms de points de hook utilisés |
| `has_blueprint` | bool | `false` | true si Flask Blueprint présent |
| `blueprint_prefix` | string | `""` | Préfixe d'URL du Blueprint (ex : `"/ext/my-plugin"`) |
| `nav` | object | `null` | Configuration du lien de navigation |
| `config` | object | `{}` | Paramètres de base |
| `config_schema` | object | `{}` | Schéma de paramètres utilisateur |

## Objet `config`

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `enabled` | bool | `true` | État actif initial |
| `priority` | int | `500` | Ordre de chargement (valeurs faibles chargées en premier) |

## Objet `nav`

| Champ | Type | Description |
|---|---|---|
| `label` | string | Étiquette affichée dans la navigation |
| `icon` | string | Icône emoji (ex : `"🔌"`) |

Si `nav` est défini, configurer aussi `has_blueprint: true` et `blueprint_prefix`.

## Objet `config_schema`

Définit les paramètres modifiables par l'utilisateur depuis l'UI Settings. Chaque clé devient un champ de paramètre.

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

### Définition de Champ

| Propriété | Type | Description |
|---|---|---|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Valeur par défaut |
| `label` | string | Nom affiché dans l'UI (utilise le nom de clé si omis) |
| `description` | string | Texte d'aide |

### Lecture/Écriture des Valeurs de Configuration

Python :
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# Lecture
val = get_extension_config_value("my-plugin", "field_name", "default")

# Écriture
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API :
```
GET  /api/extensions/<name>/config    — Obtenir le schéma et les valeurs actuelles
POST /api/extensions/<name>/config    — Enregistrer avec {"values": {"key": "val"}}
```

## Exemple Complet

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
