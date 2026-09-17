# Settings API

管理應用程式設定、秘密加密，以及外部密碼管理器整合（1Password / Bitwarden）的 API。

秘密值在 GET 回應中一律以遮罩形式（`****`）回傳。`source` 欄位表示該值從哪個後端解析而來。

## 認證

所有端點皆需要 PIN 認證或 API Key 認證。

---

## GET /api/settings/schema

取得完整的設定結構定義。回傳所有設定的鍵名、型別、預設值、分類及其他中繼資料。

### 參數

無

### 回應

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `key` | string | 設定鍵（以點號分隔，例如 `github.token`） |
| `type` | string | 值型別（`str`、`int`、`float`、`bool`） |
| `default` | any | 預設值 |
| `category` | string | 分類名稱 |
| `secret` | bool | 是否為秘密值 |
| `label` | string | 顯示標籤 |

---

## GET /api/settings/all

取得所有設定值。秘密值以遮罩形式回傳。

### 參數

無

### 回應

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `key` | string | 設定鍵 |
| `value` | any | 目前的值（秘密值會被遮罩） |
| `source` | string | 值來源：`default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | 是否為秘密值 |
| `category` | string | 分類名稱 |

---

## GET /api/settings/\<key\>

取得單一設定值。鍵使用以點號分隔的路徑格式（例如 `github.token`）。

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `key` | string | 設定鍵（路徑參數） |

### 回應

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 404 | `not_found` | 未知的設定鍵 |

---

## PUT /api/settings/\<key\>

更新設定值。秘密值會自動加密。可選擇指定 1Password URI 以在外部管理秘密。

### Rate Limit

DESTRUCTIVE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `key` | string | 設定鍵（路徑參數） |

### 請求

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `value` | any | 是 | 要設定的值。自動轉換為結構定義中的型別 |
| `op_uri` | string | 否 | 1Password URI。指定時會儲存 `op_secrets` 對應而非直接儲存值 |

### 回應

```json
{
  "key": "github.token",
  "updated": true
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `bad_request` | 請求主體缺少 `value` |
| 404 | `not_found` | 未知的設定鍵 |

---

## GET /api/settings/secrets/status

取得加密金鑰後端狀態。顯示目前使用的金鑰管理方式。

### 參數

無

### 回應

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `backend` | string | 目前的金鑰後端（`keychain` / `passphrase` / `file`） |
| `available` | bool | 加密是否可用 |
| `keychain_supported` | bool | 是否支援 OS keychain |

---

## POST /api/settings/secrets/export

將加密金鑰匯出為受密碼保護的 JSON。用於備份或遷移至其他環境。

### Rate Limit

DESTRUCTIVE

### 請求

```json
{
  "password": "my-export-password"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `password` | string | 是 | 用於保護匯出資料的密碼 |

### 回應

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `bad_request` | 請求主體缺少 `password` |
| 400 | `export_failed` | 匯出作業失敗 |

---

## POST /api/settings/secrets/import

從先前匯出的資料匯入加密金鑰。

### Rate Limit

DESTRUCTIVE

### 請求

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `export_data` | string | 是 | 匯出時取得的資料 |
| `password` | string | 是 | 匯出時設定的密碼 |

### 回應

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `bad_request` | 缺少 `export_data` 或 `password` |
| 400 | `import_failed` | 密碼錯誤或資料損毀 |

---

## POST /api/settings/secrets/migrate-keychain

將加密金鑰從檔案後端遷移至 OS keychain。支援 macOS Keychain、Windows Credential Manager 和 Linux Secret Service。

### Rate Limit

DESTRUCTIVE

### 請求

無（不需要請求主體）

### 回應

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `migration_failed` | keychain 不可用或遷移失敗 |

---

## GET /api/settings/op-status

取得 1Password CLI（`op`）連線狀態。

### 參數

無

### 回應

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `available` | bool | `op` 命令是否存在於 PATH |
| `signed_in` | bool | 是否已登入 1Password |
| `version` | string | `op` CLI 版本 |

---

## GET /api/settings/secrets/op-vaults

列出可用的 1Password vault。

### 參數

無

### 回應

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI 不可用 |

---

## POST /api/settings/secrets/push-to-op

將所有秘密設定批次寫入 1Password，並在 config.json 中儲存 `op_secrets` 對應。

### Rate Limit

DESTRUCTIVE

### 請求

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `vault` | string | 是 | 目標 1Password vault 名稱 |
| `item_title` | string | 否 | 1Password 項目標題。預設：`YU AI Manager` |
| `remove_local` | bool | 否 | 若為 `true`，推送後從 config.json 移除本地加密值。預設：`false` |

### 回應

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `bad_request` | 缺少 `vault` |
| 400 | `no_secrets` | 無秘密可推送 |
| 500 | `op_push_failed` | 寫入 1Password 失敗 |
| 503 | `op_unavailable` | 1Password CLI 不可用 |

---

## DELETE /api/settings/op-mapping/\<key\>

移除 1Password URI 對應，回復為本地加密。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `key` | string | 設定鍵（路徑參數） |

### 回應

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 404 | `not_found` | 在 `op_secrets` 對應中找不到該鍵 |

---

## GET /api/settings/bw-status

取得 Bitwarden CLI（`bw`）連線狀態。

### 參數

無

### 回應

```json
{
  "available": true,
  "status": "unlocked"
}
```

| 欄位 | 型別 | 說明 |
|-------|------|-------------|
| `available` | bool | `bw` 命令是否存在於 PATH |
| `status` | string | Bitwarden 工作階段狀態 |

---

## GET /api/settings/secrets/bw-folders

列出可用的 Bitwarden 資料夾。

### 參數

無

### 回應

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI 不可用 |

---

## POST /api/settings/secrets/push-to-bw

將所有秘密設定批次寫入 Bitwarden，並在 config.json 中儲存 `bw_secrets` 對應。

### Rate Limit

WRITE

### 請求

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| 參數 | 型別 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `folder_id` | string/null | 否 | 目標 Bitwarden 資料夾 ID。省略則不指定資料夾 |
| `item_name` | string | 否 | Bitwarden 項目名稱。預設：`YU AI Manager` |

### 回應

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 400 | `no_secrets` | 無秘密可推送 |
| 500 | `bw_push_failed` | 寫入 Bitwarden 失敗 |
| 503 | `bw_unavailable` | Bitwarden CLI 不可用 |

---

## DELETE /api/settings/bw-mapping/\<key\>

移除 Bitwarden 對應，回復為本地加密。

### Rate Limit

WRITE

### 參數

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `key` | string | 設定鍵（路徑參數） |

### 回應

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### 錯誤

| 狀態碼 | 代碼 | 說明 |
|--------|------|-------------|
| 404 | `not_found` | 在 `bw_secrets` 對應中找不到該鍵 |
