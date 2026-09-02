# 外掛開發指南

本指南介紹如何為 YU AI Manager 開發外掛（Extension）。

## 最小設定

只需在 `extensions/` 目錄下建立一個資料夾並放置兩個檔案，外掛即可運作。

```
extensions/
  my-plugin/
    extension.json      # 清單（必要）
    my_plugin.py        # 進入點（必要）
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
    """Extension 載入器呼叫的進入點。"""
    return bp
```

只要模組公開了 `get_blueprint()`，Extension 系統就會自動註冊 Blueprint。

## 新增 API 路由

外掛可以新增自己的 API 端點。

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- 建議使用 `/ext/<plugin-name>/` 作為 URL 前綴以避免衝突。
- 在 `extension.json` 中設定 `"blueprint_prefix": "/ext/my-plugin"` 後，連結會自動顯示在導覽中。

## 範本（UI 頁面）

外掛可以包含自己的 HTML 頁面。

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

範本可以繼承現有的 `_nav.html` 以維持一致的外觀：

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

## 設定架構 (config_schema)

在 `extension.json` 中定義 `config_schema`，使用者可以在設定 > Extensions 中修改外掛設定。

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

從 Python 讀取設定值：

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## 鉤子

Extension 可以鉤入特定的處理點。

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

Extension Manager 會自動發現 Python 模組中定義的鉤子函式。

## 新增導覽連結

在 `extension.json` 中加入 `nav` 欄位，側邊欄會自動顯示連結。

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

## 透過 Git 儲存庫發布

將外掛作為 Git 儲存庫發布後，使用者可以在設定 > Extensions > Install 中輸入 URL 進行安裝。

### 儲存庫結構

```
my-plugin/
  extension.json     # 放在根目錄
  my_plugin.py
  templates/
  README.md
```

### 安裝流程

1. 使用者在設定 > Extensions > Install 中輸入 Git URL。
2. 系統使用 `git clone --depth 1` 複製儲存庫。
3. 驗證 `extension.json`。
4. 將外掛放置在 `extensions/` 目錄下。
5. 重新啟動伺服器後外掛被啟用。

### 市集註冊

在 `config.json` 的 `extension_index_url` 中設定索引 JSON 的 URL，使用者即可在 Marketplace 標籤頁中瀏覽和安裝外掛。

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

## CSS 前綴慣例

使用外掛專用的 CSS 類別前綴以防止樣式衝突：

```css
.mp-container { ... }
.mp-card { ... }
```

## 安全注意事項

- 切勿將使用者輸入直接嵌入 SQL，請使用 `?` 佔位符。
- 防範檔案路徑的路徑遍歷攻擊。
- 外部 API 呼叫時設定 User-Agent 標頭。
- 現有的全域攔截器會自動注入 CSRF 標頭（`X-Requested-With`）。
