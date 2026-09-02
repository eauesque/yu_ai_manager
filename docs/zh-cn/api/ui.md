# UI Management API

用于列出、切换、安装和卸载 UI 主题的 API。

## GET /api/ui/list

列出所有已安装的 UI。返回每个 UI 的 manifest 信息、激活状态，以及模板/静态文件是否存在。

### Parameters

无

### Response

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | UI 目录名称 |
| `active` | boolean | 是否为当前激活的 UI |
| `manifest` | object | `manifest.json` 的内容 |
| `has_templates` | boolean | 是否存在 `templates/` 目录 |
| `has_static` | boolean | 是否存在 `static/` 目录 |

## POST /api/ui/switch

切换激活的 UI。更改会保存到 `config.json`，需要重启服务器才能生效。

### Rate Limit

WRITE

### Request

```json
{
  "name": "custom-dark"
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 目标 UI 名称。仅允许字母数字、连字符和下划线 |

### Response

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errors

| 状态码 | 条件 |
|--------|------|
| 400 | UI 名称为空或包含无效字符 |
| 404 | 指定的 UI 不存在 |
| 400 | `manifest.json` 缺失或无效 |
| 500 | 无法保存 `config.json` |

## POST /api/ui/install

从 URL 安装 UI。**仅允许从 localhost 访问。**

### Rate Limit

WRITE

### Authentication

需要 PIN 或 API Key 认证，且请求必须来自 localhost。远程请求会返回 403 被拒绝。

### Request

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| 参数 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `url` | string | 是 | UI 包的 URL（zip 压缩包等） |

### Response

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errors

| 状态码 | 条件 |
|--------|------|
| 400 | URL 为空 |
| 403 | 请求非来自 localhost |

## DELETE /api/ui/<name>/uninstall

卸载 UI。**仅允许从 localhost 访问。**默认 UI（`default`）不能被移除。

如果被卸载的 UI 是当前激活的，`config.json` 中的 UI 设置会被重置，并恢复为默认 UI。

### Rate Limit

WRITE

### Authentication

需要 PIN 或 API Key 认证，且请求必须来自 localhost。远程请求会返回 403 被拒绝。

### Parameters

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | UI 名称（路径参数）。仅允许字母数字、连字符和下划线 |

### Response

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errors

| 状态码 | 条件 |
|--------|------|
| 400 | 无效的 UI 名称，或尝试卸载 `default` |
| 403 | 请求非来自 localhost |
| 404 | 指定的 UI 不存在 |
