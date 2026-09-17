# Referência de Manifest

Especificação completa do arquivo manifest.json para plugins.

## Schema

```json
{
  "name": "string (required)",
  "version": "semver (required)",
  "author": "string",
  "description": "string",
  "entry_point": "string (required)",
  "homepage": "string",
  "repository": "string",
  "license": "string",
  "icon": "string (path or URL)",
  "requires": {
    "python": "string",
    "core": "string"
  },
  "permissions": ["string"],
  "hooks": ["string"],
  "ui": {
    "routes": [
      {
        "path": "/my-page",
        "template": "pages/my_page.html"
      }
    ],
    "menu_items": [
      {
        "label": "My Menu",
        "action": "navigate:/my-page"
      }
    ]
  },
  "config": {
    "setting1": {
      "type": "string",
      "default": "value"
    }
  }
}
```

## Campos

### Obrigatórios

| Campo | Tipo | Exemplo |
|-------|------|---------|
| `name` | string | `"my-plugin"` |
| `version` | semver | `"1.0.0"` |
| `entry_point` | string | `"plugin.py:MyPlugin"` |

### Opcionais

| Campo | Tipo | Uso |
|-------|------|-----|
| `author` | string | Crédito |
| `description` | string | Descrição breve |
| `icon` | string | Ícone no UI |
| `homepage` | string | Link de documentação |
| `requires` | object | Dependências |
| `permissions` | array | Segurança |
| `hooks` | array | Lifecycle |
| `ui` | object | Interface |
| `config` | object | Configurações |

## Permissões

Valores válidos:

- `read_images`
- `write_metadata`
- `execute_ai`
- `access_network`
- `access_filesystem`
- `create_ui`

## Hooks

Hooks disponíveis:

- `on_init`
- `on_shutdown`
- `on_scan_complete`
- `on_image_added`
- `on_image_deleted`

## Configuração

```json
"config": {
  "api_key": {
    "type": "string",
    "required": true,
    "description": "API key"
  },
  "timeout": {
    "type": "integer",
    "default": 30,
    "min": 1,
    "max": 300
  },
  "enabled": {
    "type": "boolean",
    "default": true
  }
}
```

Usuários podem configurar em Settings > Plugins > [Plugin].

## Validação

Use `yu-cli validate-manifest manifest.json` para validar.

