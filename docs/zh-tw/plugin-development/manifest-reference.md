# extension.json 清單參考

此清單檔案定義 Extension 的中繼資料和設定。放置在 `extensions/<name>/extension.json`。

## 必要欄位

| 欄位 | 類型 | 說明 |
|------|------|------|
| `name` | string | Extension 的唯一識別碼。應與目錄名稱一致 |
| `version` | string | 語意化版本（例如 `"1.0.0"`） |
| `entry` | string | Python 進入點檔案名稱（例如 `"my_plugin.py"`） |

## 選用欄位

| 欄位 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `description` | string | `""` | 簡短說明（顯示在 UI 卡片上） |
| `author` | string | `""` | 作者名稱 |
| `type` | string | `"general"` | Extension 類型：`"general"`、`"ui_widget"`、`"parser"`、`"analyzer"` |
| `hooks` | string[] | `[]` | 要使用的鉤子點名稱陣列 |
| `has_blueprint` | bool | `false` | 如果 Extension 有 Flask Blueprint 則設為 true |
| `blueprint_prefix` | string | `""` | Blueprint 的 URL 前綴（例如 `"/ext/my-plugin"`） |
| `nav` | object | `null` | 導覽連結設定 |
| `config` | object | `{}` | 基本設定 |
| `config_schema` | object | `{}` | 面向使用者的設定架構 |

## `config` 物件

| 欄位 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 初始啟用狀態 |
| `priority` | int | `500` | 載入順序（較小的值優先載入） |

## `nav` 物件

| 欄位 | 類型 | 說明 |
|------|------|------|
| `label` | string | 導覽中顯示的標籤 |
| `icon` | string | Emoji 圖示（例如 `"🔌"`） |

設定 `nav` 時還應設定 `has_blueprint: true` 和 `blueprint_prefix`。

## `config_schema` 物件

定義可從設定 UI 存取的使用者可編輯設定。每個鍵成為一個設定欄位。

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

### 欄位定義

| 屬性 | 類型 | 說明 |
|------|------|------|
| `type` | string | `"string"`、`"number"`、`"integer"`、`"boolean"` |
| `default` | any | 預設值 |
| `label` | string | UI 中的顯示名稱（省略時回退到鍵名） |
| `description` | string | 說明文字 |

### 讀寫設定值

Python：
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# 讀取
val = get_extension_config_value("my-plugin", "field_name", "default")

# 寫入
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API：
```
GET  /api/extensions/<name>/config    -- 取得架構和目前值
POST /api/extensions/<name>/config    -- 使用 {"values": {"key": "val"}} 儲存
```

## 完整範例

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
