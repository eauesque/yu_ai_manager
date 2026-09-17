# Руководство по разработке плагинов

Руководство по разработке плагинов (Extension) для YU AI Manager.

## Минимальная структура

Плагин создаётся в директории `extensions/` с двумя обязательными файлами:

```
extensions/
  my-plugin/
    extension.json      # Манифест (обязателен)
    my_plugin.py        # Точка входа (обязательна)
```

### extension.json (минимум)

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

### my_plugin.py (минимум)

```python
"""My Plugin — минимальный пример"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Точка входа, вызываемая загрузчиком Extension."""
    return bp
```

Достаточно опубликовать `get_blueprint()` — Extension-система автоматически зарегистрирует Blueprint.

## Добавление API-маршрутов

Из плагина можно добавлять собственные API-эндпоинты:

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- Рекомендуется URL-префикс `/ext/<plugin-name>/` (для предотвращения коллизий)
- При установке `"blueprint_prefix": "/ext/my-plugin"` в `extension.json` ссылка добавляется в навигацию автоматически

## Шаблоны (UI-страницы)

Плагины могут иметь собственные HTML-страницы:

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
```

В шаблонах можно расширять `_nav.html` для единообразного оформления:

```html
{% extends "_nav.html" %}
{% block title %}My Plugin{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>My Plugin</h1>
</div>
{% endblock %}
```

## Схема конфигурации (config_schema)

Для возможности изменения настроек плагина через Settings > Extensions добавьте `config_schema` в `extension.json`:

```json
{
  "config_schema": {
    "greeting": { "type": "string", "default": "Hello" },
    "max_items": { "type": "number", "default": 10 },
    "verbose": { "type": "boolean", "default": false }
  }
}
```

Чтение настроек из Python:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## Хуки

Extension могут вставлять обработку в точки хуков:

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

## Добавление в навигацию

Поле `nav` в `extension.json` автоматически добавляет ссылку в боковую панель:

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

## Публикация в Git-репозитории

Опубликуйте плагин в Git-репозитории — пользователи смогут установить его, введя URL в Settings > Extensions > Install.

### Структура репозитория

```
my-plugin/
  extension.json     # В корне
  my_plugin.py
  templates/
  README.md
```

## Соглашения по CSS-префиксам

Используйте уникальный префикс для предотвращения конфликтов стилей:

```css
.mp-container { ... }
.mp-card { ... }
```

## Примечания по безопасности

- Не встраивать пользовательский ввод напрямую в SQL (использовать плейсхолдеры `?`)
- Внимание к атакам путей в именах файлов (path traversal)
- Устанавливать User-Agent при вызовах внешних API
- Заголовок CSRF (`X-Requested-With`) автоматически добавляется глобальным перехватчиком
