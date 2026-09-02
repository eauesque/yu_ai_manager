# extension.json マニフェストリファレンス

Extension のメタ情報と設定を定義するマニフェストファイルです。`extensions/<name>/extension.json` に配置します。

## 必須フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `name` | string | Extension の一意な識別名。ディレクトリ名と一致させること |
| `version` | string | セマンティックバージョン (例: `"1.0.0"`) |
| `entry` | string | Python エントリポイントファイル名 (例: `"my_plugin.py"`) |

## オプションフィールド

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `description` | string | `""` | 短い説明文 (UI のカード表示に使用) |
| `author` | string | `""` | 作者名 |
| `type` | string | `"general"` | Extension タイプ: `"general"`, `"ui_widget"`, `"parser"`, `"analyzer"` |
| `hooks` | string[] | `[]` | 使用するフックポイント名の配列 |
| `has_blueprint` | bool | `false` | Flask Blueprint を持つ場合 true |
| `blueprint_prefix` | string | `""` | Blueprint の URL プレフィックス (例: `"/ext/my-plugin"`) |
| `nav` | object | `null` | ナビゲーションリンク設定 |
| `config` | object | `{}` | 基本設定 |
| `config_schema` | object | `{}` | ユーザー設定スキーマ |

## `config` オブジェクト

| フィールド | 型 | デフォルト | 説明 |
|---|---|---|---|
| `enabled` | bool | `true` | 初期有効状態 |
| `priority` | int | `500` | ロード順序 (小さい値が先にロード) |

## `nav` オブジェクト

| フィールド | 型 | 説明 |
|---|---|---|
| `label` | string | ナビゲーションに表示するラベル |
| `icon` | string | 絵文字アイコン (例: `"🔌"`) |

`nav` を設定した場合、`has_blueprint: true` と `blueprint_prefix` も設定してください。

## `config_schema` オブジェクト

ユーザーが Settings UI から変更可能な設定を定義します。各キーが設定フィールドになります。

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

### フィールド定義

| プロパティ | 型 | 説明 |
|---|---|---|
| `type` | string | `"string"`, `"number"`, `"integer"`, `"boolean"` |
| `default` | any | デフォルト値 |
| `label` | string | UI 表示名 (省略時はキー名を使用) |
| `description` | string | ヘルプテキスト |

### 設定値の読み書き

Python:
```python
from core.extensions_core.extensions_admin import (
    get_extension_config_value,
    save_extension_config_values,
)

# 読み取り
val = get_extension_config_value("my-plugin", "field_name", "default")

# 書き込み
save_extension_config_values("my-plugin", {"field_name": "new_value"})
```

API:
```
GET  /api/extensions/<name>/config    — スキーマと現在値を取得
POST /api/extensions/<name>/config    — {"values": {"key": "val"}} で保存
```

## 完全な例

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
