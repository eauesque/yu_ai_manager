# 插件开发指南

本指南介绍如何为 YU AI Manager 开发插件（Extension）。

## 最小设置

只需在 `extensions/` 目录下创建一个文件夹并放置两个文件，插件即可运行。

```
extensions/
  my-plugin/
    extension.json      # 清单（必需）
    my_plugin.py        # 入口点（必需）
```

### extension.json（最小）

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

### my_plugin.py（最小）

```python
"""My Plugin -- minimal example"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Extension 加载器调用的入口点。"""
    return bp
```

只要模块暴露了 `get_blueprint()`，Extension 系统就会自动注册 Blueprint。

## 添加 API 路由

插件可以添加自己的 API 端点。

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- 建议使用 `/ext/<plugin-name>/` 作为 URL 前缀以避免冲突。
- 在 `extension.json` 中设置 `"blueprint_prefix": "/ext/my-plugin"` 后，链接会自动显示在导航中。

## 模板（UI 页面）

插件可以包含自己的 HTML 页面。

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

模板可以继承现有的 `_nav.html` 以保持一致的外观：

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

## 配置架构 (config_schema)

在 `extension.json` 中定义 `config_schema`，用户可以在设置 > Extensions 中修改插件设置。

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

从 Python 读取配置值：

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## 钩子

Extension 可以钩入特定的处理点。

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Extension Manager 会自动发现 Python 模块中定义的钩子函数。

## 添加导航链接

在 `extension.json` 中添加 `nav` 字段，侧边栏会自动显示链接。

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

## 通过 Git 仓库发布

将插件作为 Git 仓库发布后，用户可以在设置 > Extensions > Install 中输入 URL 进行安装。

### 仓库结构

```
my-plugin/
  extension.json     # 放在根目录
  my_plugin.py
  templates/
  README.md
```

### 安装流程

1. 用户在设置 > Extensions > Install 中输入 Git URL。
2. 系统使用 `git clone --depth 1` 克隆仓库。
3. 验证 `extension.json`。
4. 将插件放置在 `extensions/` 目录下。
5. 重启服务器后插件被激活。

### 市场注册

在 `config.json` 的 `extension_index_url` 中设置索引 JSON 的 URL，用户即可在 Marketplace 标签页中浏览和安装插件。

索引 JSON 格式：

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

## CSS 前缀约定

使用插件专用的 CSS 类前缀以防止样式冲突：

```css
.mp-container { ... }
.mp-card { ... }
```

## 安全注意事项

- 切勿将用户输入直接嵌入 SQL，请使用 `?` 占位符。
- 防范文件路径的路径遍历攻击。
- 外部 API 调用时设置 User-Agent 头。
- 现有的全局拦截器会自动注入 CSRF 头（`X-Requested-With`）。
