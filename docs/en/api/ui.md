# UI Management API

APIs for listing, switching, installing, and uninstalling UI themes.

## GET /api/ui/list

List all installed UIs. Returns manifest information, active status, and whether templates/static files exist for each UI.

### Parameters

None

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

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | UI directory name |
| `active` | boolean | Whether this is the currently active UI |
| `manifest` | object | Contents of `manifest.json` |
| `has_templates` | boolean | Whether a `templates/` directory exists |
| `has_static` | boolean | Whether a `static/` directory exists |

## POST /api/ui/switch

Switch the active UI. The change is saved to `config.json` and requires a server restart to take effect.

### Rate Limit

WRITE

### Request

```json
{
  "name": "custom-dark"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Target UI name. Only alphanumeric characters, hyphens, and underscores are allowed |

### Response

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errors

| Status | Condition |
|--------|-----------|
| 400 | UI name is empty or contains invalid characters |
| 404 | Specified UI does not exist |
| 400 | `manifest.json` is missing or invalid |
| 500 | Failed to save `config.json` |

## POST /api/ui/install

Install a UI from a URL. **Only allowed from localhost.**

### Rate Limit

WRITE

### Authentication

Requires PIN or API Key authentication, plus the request must originate from localhost. Remote requests are rejected with 403.

### Request

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL of the UI package (zip archive, etc.) |

### Response

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errors

| Status | Condition |
|--------|-----------|
| 400 | URL is empty |
| 403 | Request is not from localhost |

## DELETE /api/ui/<name>/uninstall

Uninstall a UI. **Only allowed from localhost.** The default UI (`default`) cannot be removed.

If the uninstalled UI is currently active, the UI setting in `config.json` is reset and the default UI is restored.

### Rate Limit

WRITE

### Authentication

Requires PIN or API Key authentication, plus the request must originate from localhost. Remote requests are rejected with 403.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | UI name (path parameter). Only alphanumeric characters, hyphens, and underscores |

### Response

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errors

| Status | Condition |
|--------|-----------|
| 400 | Invalid UI name, or attempted to uninstall `default` |
| 403 | Request is not from localhost |
| 404 | Specified UI does not exist |
