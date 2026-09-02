# Справочник манифеста extension.json

Файл манифеста, определяющий метаданные и конфигурацию Extension.
Размещается в `extensions/<name>/extension.json`.

## Обязательные поля

| Поле | Тип | Описание |
|------|-----|---------|
| `name` | string | Уникальный идентификатор Extension. Должен совпадать с именем директории |
| `version` | string | Семантическая версия (например, `"1.0.0"`) |
| `entry` | string | Имя файла точки входа Python (например, `"my_plugin.py"`) |

## Опциональные поля

| Поле | Тип | По умолч. | Описание |
|------|-----|----------|---------|
| `description` | string | `""` | Краткое описание (отображается на карточке UI) |
| `author` | string | `""` | Имя автора |
| `type` | string | `"general"` | Тип Extension: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | Массив имён используемых точек хуков |
| `has_blueprint` | bool | `false` | true при наличии Flask Blueprint |
| `blueprint_prefix` | string | `""` | URL-префикс Blueprint (например, `"/ext/my-plugin"`) |
| `nav` | object | `null` | Настройка ссылки в навигации |
| `config` | object | `{}` | Базовые настройки |
| `config_schema` | object | `{}` | Схема пользовательских настроек |

## Объект `config`

| Поле | Тип | По умолч. | Описание |
|------|-----|----------|---------|
| `enabled` | bool | `true` | Начальное состояние включения |
| `priority` | int | `500` | Порядок загрузки (меньшее значение загружается первым) |

## Объект `nav`

| Поле | Тип | Описание |
|------|-----|---------|
| `label` | string | Метка в навигации |
| `icon` | string | Иконка-эмодзи (например, `"🔌"`) |

## Объект `config_schema`

Определяет настройки, доступные для изменения через Settings UI. Каждый ключ — поле настройки.

```json
{
  "config_schema": {
    "field_name": {
      "type": "string",
      "default": "value",
      "label": "Display Name",
      "description": "Help text"
    }
  }
}
```

### Определение поля

| Свойство | Тип | Описание |
|---------|-----|---------|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | Значение по умолчанию |
| `label` | string | Отображаемое имя в UI (если не указано — используется имя ключа) |
| `description` | string | Текст подсказки |

## Полный пример

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
