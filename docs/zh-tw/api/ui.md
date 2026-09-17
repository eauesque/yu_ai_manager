# UI Management API

用於列出、切換、安裝和解除安裝 UI 主題的 API。

## GET /api/ui/list

列出所有已安裝的 UI。回傳每個 UI 的 manifest 資訊、啟用狀態，以及範本/靜態檔案是否存在。

### Parameters

無

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

| 欄位 | 型別 | 說明 |
|------|------|------|
| `name` | string | UI 目錄名稱 |
| `active` | boolean | 是否為目前啟用的 UI |
| `manifest` | object | `manifest.json` 的內容 |
| `has_templates` | boolean | 是否存在 `templates/` 目錄 |
| `has_static` | boolean | 是否存在 `static/` 目錄 |

## POST /api/ui/switch

切換啟用的 UI。變更會儲存到 `config.json`，需要重新啟動伺服器才會生效。

### Rate Limit

WRITE

### Request

```json
{
  "name": "custom-dark"
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `name` | string | 是 | 目標 UI 名稱。僅允許英數字元、連字號和底線 |

### Response

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errors

| 狀態碼 | 條件 |
|--------|------|
| 400 | UI 名稱為空或包含無效字元 |
| 404 | 指定的 UI 不存在 |
| 400 | `manifest.json` 遺失或無效 |
| 500 | 無法儲存 `config.json` |

## POST /api/ui/install

從 URL 安裝 UI。**僅限從 localhost 存取。**

### Rate Limit

WRITE

### Authentication

需要 PIN 或 API Key 認證，且請求必須來自 localhost。遠端請求會回傳 403 被拒絕。

### Request

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| 參數 | 型別 | 必須 | 說明 |
|------|------|------|------|
| `url` | string | 是 | UI 套件的 URL（zip 壓縮檔等） |

### Response

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errors

| 狀態碼 | 條件 |
|--------|------|
| 400 | URL 為空 |
| 403 | 請求非來自 localhost |

## DELETE /api/ui/<name>/uninstall

解除安裝 UI。**僅限從 localhost 存取。**預設 UI（`default`）無法被移除。

如果被解除安裝的 UI 是目前啟用的，`config.json` 中的 UI 設定會被重設，並恢復為預設 UI。

### Rate Limit

WRITE

### Authentication

需要 PIN 或 API Key 認證，且請求必須來自 localhost。遠端請求會回傳 403 被拒絕。

### Parameters

| 參數 | 型別 | 說明 |
|------|------|------|
| `name` | string | UI 名稱（路徑參數）。僅允許英數字元、連字號和底線 |

### Response

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errors

| 狀態碼 | 條件 |
|--------|------|
| 400 | 無效的 UI 名稱，或嘗試解除安裝 `default` |
| 403 | 請求非來自 localhost |
| 404 | 指定的 UI 不存在 |
