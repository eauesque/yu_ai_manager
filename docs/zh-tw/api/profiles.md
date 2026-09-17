# Profiles API

設定檔管理 API。Profile 是應用程式設定的命名快照，儲存為 `profiles/<name>.json`。

所有端點需要 PIN 認證。PIN 認證停用時回傳 403，會話未認證時回傳 401。

## Profile 名稱規則

- 1 至 64 個字元
- 允許的字元：`a-zA-Z0-9_-`

---

## GET /api/profiles

列出所有 Profile 的中繼資料。依收藏優先排序，然後依標籤字母順序排列。

### 參數

無

### 回應

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（用作檔案名稱） |
| `label` | string | 顯示標籤 |
| `description` | string | 說明文字 |
| `favorite` | boolean | 收藏旗標 |
| `last_used_at` | string/null | 最後使用時間戳（ISO 8601） |
| `created_at` | string/null | 建立時間戳（ISO 8601） |
| `db` | string/null | 關聯的資料庫路徑 |
| `is_active` | boolean | 是否為目前使用中的 Profile |

## GET /api/profiles/\<name\>

取得指定 Profile 的完整資料。

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（路徑參數） |

### 回應

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_profile_name` | 400 | Profile 名稱無效 |
| `profile_not_found` | 404 | Profile 不存在 |

## POST /api/profiles

建立新的 Profile。

### Rate Limit

WRITE

### 請求

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `name` | string | 是 | Profile 名稱（`a-zA-Z0-9_-`，1-64 字元） |
| `label` | string | 否 | 顯示標籤。省略時預設為 `name` |
| `description` | string | 否 | 說明文字 |
| `base_config` | object | 否 | 初始設定值。中繼資料鍵（`name`、`label`、`description`、`favorite`、`last_used_at`、`created_at`、`db`）以外的鍵會被複製到 Profile 中 |

### 回應 (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_profile_name` | 400 | Profile 名稱無效 |
| `invalid_label` | 400 | 標籤為空 |
| `profile_exists` | 409 | 同名的 Profile 已存在 |

## PUT /api/profiles/\<name\>

更新 Profile 中繼資料。僅可變更 `label`、`description` 和 `favorite`。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（路徑參數） |

### 請求

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `label` | string | 否 | 顯示標籤 |
| `description` | string | 否 | 說明文字 |
| `favorite` | boolean | 否 | 收藏旗標 |

至少需要提供一個欄位。

### 回應

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `empty_update` | 400 | 未指定要更新的欄位 |
| `update_failed` | 400 | 找不到 Profile 等 |

## DELETE /api/profiles/\<name\>

刪除 Profile。無法刪除目前使用中的 Profile。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（路徑參數） |

### 回應

```json
{
  "deleted": "my_profile"
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `delete_active` | 400 | 無法刪除使用中的 Profile |
| `delete_failed` | 400 | 找不到 Profile 等 |

## POST /api/profiles/\<name\>/duplicate

以新名稱複製 Profile。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | 來源 Profile 名稱（路徑參數） |

### 請求

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `new_name` | string | 是 | 新的 Profile 名稱 |
| `new_label` | string | 否 | 新的顯示標籤。省略時預設為 `new_name` |

### 回應 (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `duplicate_failed` | 400 | 找不到來源、新名稱無效或名稱已存在 |

## POST /api/profiles/\<name\>/rename

重新命名 Profile。如果重新命名的是使用中的 Profile，`config.json` 中的 `active_profile` 會自動更新。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | 目前的 Profile 名稱（路徑參數） |

### 請求

```json
{
  "new_name": "renamed_profile"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `new_name` | string | 是 | 新的 Profile 名稱 |

### 回應

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_profile_name` | 400 | 新的 Profile 名稱無效 |
| `rename_failed` | 400 | 找不到來源 Profile 或新名稱已存在 |

## POST /api/profiles/\<name\>/favorite

切換 Profile 的收藏狀態。反轉目前的 `favorite` 值。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（路徑參數） |

### 請求

不需要請求主體。

### 回應

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `profile_not_found` | 404 | Profile 不存在 |
| `favorite_failed` | 400 | 更新失敗 |

---

## QR 匯出 / 匯入

將 Profile 匯出為 JSON 字串以供 QR 碼使用，或從 QR 碼匯入 Profile。匯出時會自動過濾包含 `pin`、`token`、`secret` 或 `key` 的敏感欄位。

## GET /api/profiles/\<name\>/export

將 Profile 匯出為 QR 碼用的 JSON 字串。敏感欄位會被排除。

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | Profile 名稱（路徑參數） |

### 回應

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` 是用於嵌入 QR 碼的 JSON 字串。`schema` 欄位標識格式版本。

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `profile_not_found` | 404 | Profile 不存在 |

## POST /api/profiles/import-preview

預覽 QR 資料的匯入。用於檢查與現有 Profile 的差異。不會實際執行匯入。

### Rate Limit

WRITE

### 請求

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `qr_data` | string/object | 是 | QR 碼的 JSON 字串或已解析的物件 |

### 回應（新的 Profile）

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### 回應（已存在的 Profile）

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_qr` | 400 | 無效的 QR 資料或缺少 `profile` 鍵 |
| `invalid_profile_name` | 400 | Profile 名稱無效 |

## POST /api/profiles/import

從 QR 資料匯入 Profile。支援三種模式：建立新的、差異合併和完整覆寫。

### Rate Limit

WRITE

### 請求

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `qr_data` | string/object | 是 | QR 碼的 JSON 字串或已解析的物件 |
| `mode` | string | 否 | 匯入模式：`full`（完整覆寫，預設）、`diff`（僅合併變更的鍵）、`new`（僅建立新的） |

### 回應

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

建立新 Profile 時回傳狀態碼 201。

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_qr` | 400 | 無效的 QR 資料 |
| `invalid_profile_name` | 400 | Profile 名稱無效 |
| `profile_exists` | 409 | `mode=new` 時 Profile 已存在 |
| `import_failed` | 400 | 匯入失敗 |
