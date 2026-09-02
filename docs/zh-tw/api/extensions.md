# Extensions API

管理 Extension 的安裝、安全性與開發的 API。

---

## GET /api/extensions

列出所有已安裝的 Extension。

### 參數

無

### 回應

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `extensions` | array | Extension 資訊陣列 |
| `total` | int | Extension 總數 |
| `category_order` | string[] | 分類顯示順序 |

## GET /api/extensions/\<name\>

取得特定 Extension 的詳細資訊。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### 錯誤

- `404` — 找不到 Extension

## POST /api/extensions/\<name\>/toggle

切換 Extension 的啟用/停用狀態。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 請求

```json
{
  "enabled": true
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `enabled` | boolean | 否 | `true` 啟用、`false` 停用。省略時切換目前狀態（反轉） |

### 回應

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### 錯誤

- `404` — 找不到 Extension

## GET /api/extensions/\<name\>/config

取得 Extension 的設定結構與目前的值。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### 錯誤

- `404` — 找不到 Extension

## POST /api/extensions/\<name\>/config

儲存 Extension 設定值。包含驗證功能。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 請求

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `values` | object | 是 | 欄位鍵與值的對應 |

### 回應

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### 錯誤

- `404` — 找不到 Extension
- `400` — 驗證錯誤

---

## Extension 安裝 / 更新 / 解除安裝

以下端點僅限 **localhost 存取**。遠端請求會回傳 `403`。

## POST /api/extensions/install

從 Git 儲存庫安裝 Extension。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 請求

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `url` | string | 是 | Git 儲存庫 URL。`git` 和 `repo` 可作為別名使用 |

### 回應

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### 錯誤

- `400` — 未提供 URL 或 URL 格式無效
- `403` — 非 localhost 存取

## POST /api/extensions/\<name\>/update

將特定 Extension 更新至最新版本（git pull）。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### 錯誤

- `403` — 非 localhost 存取
- `404` — 找不到 Extension

## POST /api/extensions/update-all

批次更新所有透過 Git 安裝的 Extension。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 回應

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### 錯誤

- `403` — 非 localhost 存取

## DELETE /api/extensions/\<name\>/uninstall

解除安裝 Extension（刪除目錄）。

### Rate Limit

DESTRUCTIVE

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### 錯誤

- `403` — 非 localhost 存取
- `404` — 找不到 Extension

---

## 安全性與權限

## GET /api/extensions/\<name\>/permissions

取得 Extension 的權限資訊與核准狀態。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `trust_level` | string | 信任等級（`trusted`、`L1`、`L2`） |
| `approved` | boolean | 使用者是否已核准此 Extension |
| `permissions.required` | array | 必要權限清單 |
| `permissions.optional` | array | 選用權限清單 |
| `granted` | object/null | 已授予權限的詳細資訊。未核准時為 `null` |

### 錯誤

- `404` — 找不到 Extension

## POST /api/extensions/\<name\>/permissions

核准或撤銷 Extension 權限。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 請求（核准）

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 請求（撤銷）

```json
{
  "action": "revoke"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `action` | string | 否 | `"approve"`（預設）或 `"revoke"` |
| `granted` | string[] | 否 | 要授予的權限名稱清單（用於核准） |
| `denied` | string[] | 否 | 要拒絕的權限名稱清單（用於核准） |

### 回應（核准）

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### 回應（撤銷）

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### 錯誤

- `400` — `granted` 不是清單
- `404` — 找不到 Extension

## GET /api/extensions/\<name\>/scan-results

取得 Extension 程式碼的靜態分析結果。回傳 ManifestAuthority 和 CodeVerifier 的結果。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `manifest_review.approved` | boolean | manifest 是否通過審查 |
| `manifest_review.issues` | array | 問題清單（`severity`、`message`） |
| `code_scan` | object/null | 程式碼掃描結果。無目錄時為 `null` |
| `code_scan.findings` | array | 發現清單 |

### 錯誤

- `404` — 找不到 Extension

## POST /api/extensions/\<name\>/rescan

重新掃描 Extension 程式碼。回傳格式與 `scan-results` 相同。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

格式與 `GET /api/extensions/<name>/scan-results` 相同。

## GET /api/extensions/\<name\>/tokens

取得 Extension 的 capability token 發行狀態。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### 錯誤

- `404` — 找不到 Extension

## GET /api/extensions/\<name\>/integrity

取得 Extension 的檔案完整性狀態。同時包含 revocation tracker 和 import guard 資訊。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `integrity` | object | 檔案完整性檢查結果 |
| `revocation` | object | Token revocation tracker 資訊 |
| `import_guard` | object | Import guard 拒絕次數 |

### 錯誤

- `404` — 找不到 Extension

---

## Hook 與 Marketplace

## GET /api/extensions/hooks

列出已註冊的 Extension hook 和 hook 定義。

### 參數

無

### 回應

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `hooks` | object | hook 名稱與已註冊 Extension 清單的對應 |
| `definitions` | object | 可用的 hook 定義。`mode` 為執行模式 |

## GET /api/extensions/marketplace

搜尋 Marketplace Extension。

### 參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `q` | string | 否 | 搜尋查詢（查詢參數）。空字串回傳全部 |

### 回應

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `extensions` | array | Marketplace Extension 資訊 |
| `extensions[].installed` | boolean | 是否已在本機安裝 |
| `total` | int | 搜尋結果總數 |

## POST /api/extensions/marketplace/refresh

強制重新整理 Marketplace 快取。

### Rate Limit

WRITE

### 回應

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## 隔離

## GET /api/extensions/isolation

取得處理程序隔離狀態。

### 參數

無

### 回應

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `available` | boolean | 處理程序隔離是否可用 |
| `processes` | object | Extension 名稱與處理程序狀態的對應 |

## GET /api/extensions/os-isolation

取得作業系統層級的隔離狀態（Phase D）。同時包含處理程序隔離資訊。

### 參數

無

### 回應

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `os_isolation` | object | 作業系統層級隔離資訊 |
| `config.enabled` | boolean | 作業系統隔離是否啟用 |
| `config.apparmor` | boolean | AppArmor（Linux）使用狀態 |
| `config.macos_sandbox_exec` | boolean | macOS sandbox-exec 使用狀態 |
| `config.macos_user_isolation` | boolean | macOS 使用者隔離使用狀態 |
| `config.windows_restricted_token` | boolean | Windows restricted token 使用狀態 |
| `config.windows_job_object` | boolean | Windows Job Object 使用狀態 |
| `processes` | object | 處理程序隔離狀態 |

---

## Extension 開發

建立與編輯自訂 Extension 的 API。基於 concession 模型，僅 `extensions/custom-{name}/` 目錄可寫入。

所有端點僅限 **localhost 存取**。

### 安全性限制

- Extension 名稱：僅限小寫英數字和連字號（`[a-z0-9-]`），最多 50 字元，禁止使用 `builtin-` 前綴
- 檔案類型：僅限白名單（`entrypoint`、`template`、`static_css`、`static_js`、`config`、`readme`）
- 二進位檔案：完全禁止
- 檔案大小限制：依類型 10KB 至 50KB

## POST /api/extensions/author/create

建立新的自訂 Extension 並產生骨架檔案。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 請求

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `name` | string | 是 | Extension 名稱（`[a-z0-9-]`，最多 50 字元） |
| `description` | string | 否 | Extension 說明 |

### 回應

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### 錯誤

- `400` — 無效名稱或 Extension 已存在
- `403` — 非 localhost 存取

## POST /api/extensions/author/\<name\>/write

寫入檔案至自訂 Extension。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數，不含 `custom-` 前綴） |

### 請求

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `file_type` | string | 是 | 檔案類型。可選：`entrypoint`、`template`、`static_css`、`static_js`、`config`、`readme` |
| `filename` | string | 是 | 不含副檔名的檔案名稱。僅限英數字、連字號和底線 |
| `content` | string | 是 | 檔案內容（僅限文字） |

### 檔案類型限制

| file_type | 副檔名 | 最大大小 | 備註 |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Extension 進入點 |
| `template` | `.html` | 50KB | 放置於 `templates/{name}/` |
| `static_css` | `.css` | 50KB | 放置於 `static/` |
| `static_js` | `.js` | 50KB | 放置於 `static/` |
| `config` | `.json` | 10KB | 檔案名稱必須為 `extension` |
| `readme` | `.md` | 20KB | 檔案名稱必須為 `README` |

### 回應

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### 錯誤

- `400` — 驗證錯誤（無效名稱、檔案類型、超過大小限制、偵測到二進位檔案）
- `403` — 非 localhost 存取

## GET /api/extensions/author/\<name\>/read

讀取自訂 Extension 的檔案。

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 查詢參數

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `file_type` | string | 是 | 檔案類型 |
| `filename` | string | 是 | 不含副檔名的檔案名稱 |

### 回應

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### 錯誤

- `400` — 驗證錯誤
- `403` — 非 localhost 存取

## GET /api/extensions/author/\<name\>/files

列出自訂 Extension 的所有檔案。

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### 錯誤

- `400` — 無效的 Extension 名稱
- `403` — 非 localhost 存取

## POST /api/extensions/author/\<name\>/validate

驗證自訂 Extension 的 extension.json 和程式碼。執行 CodeVerifier 但不會註冊 Extension。

### Rate Limit

WRITE

### 存取限制

僅限 localhost

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `name` | string | Extension 名稱（路徑參數） |

### 回應（成功）

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### 回應（發現問題）

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `ok` | boolean | 所有檢查是否通過 |
| `issues` | string[] | manifest 和程式碼驗證問題 |
| `code_findings` | array | CodeVerifier 發現 |
| `manifest` | object | 解析後的 extension.json 內容 |

### 錯誤

- `400` — 無效的 Extension 名稱或 Extension 不存在
- `403` — 非 localhost 存取
