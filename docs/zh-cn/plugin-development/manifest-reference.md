# extension.json 清单参考

此清单文件定义 Extension 的元数据和配置。放置在 `extensions/<name>/extension.json`。

## 必需字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Extension 的唯一标识符。应与目录名一致 |
| `version` | string | 语义化版本（例如 `"1.0.0"`） |
| `entry` | string | Python 入口点文件名（例如 `"my_plugin.py"`） |

## 可选字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | string | `""` | 简短描述（显示在 UI 卡片上） |
| `author` | string | `""` | 作者名称 |
| `type` | string | `"general"` | Extension 类型：`"general"`、`"ui_widget"`、`"parser"`、`"analyzer"` |
| `hooks` | string[] | `[]` | 要使用的钩子点名称数组 |
| `has_blueprint` | bool | `false` | 如果 Extension 有 Flask Blueprint 则设为 true |
| `blueprint_prefix` | string | `""` | Blueprint 的 URL 前缀（例如 `"/ext/my-plugin"`） |
| `nav` | object | `null` | 导航链接配置 |
| `config` | object | `{}` | 基本配置 |
| `config_schema` | object | `{}` | 面向用户的配置架构 |

## `config` 对象

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 初始启用状态 |
| `priority` | int | `500` | 加载顺序（较小的值优先加载） |

## `nav` 对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `label` | string | 导航中显示的标签 |
| `icon` | string | Emoji 图标（例如 `"🔌"`） |

配置 `nav` 时还应设置 `has_blueprint: true` 和 `blueprint_prefix`。

## `config_schema` 对象

定义可从设置 UI 访问的用户可编辑设置。每个键成为一个配置字段。

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

### 字段定义

| 属性 | 类型 | 说明 |
|------|------|------|
| `type` | string | `"string"`、`"number"`、`"integer"`、`"boolean"` |
| `default` | any | 默认值 |
| `label` | string | UI 中的显示名称（省略时回退到键名） |
| `description` | string | 帮助文本 |

### 读写配置值

Python：
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# 读取
val = get_extension_config_value("my-plugin", "field_name", "default")

# 写入
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API：
```
GET  /api/extensions/<name>/config    -- 获取架构和当前值
POST /api/extensions/<name>/config    -- 使用 {"values": {"key": "val"}} 保存
```

## 完整示例

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
