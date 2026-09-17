# Settings API

APIs for managing application settings, secret encryption, and external password manager integration (1Password / Bitwarden).

Secret values are always masked (`****`) in GET responses. The `source` field indicates which backend the value was resolved from.

## Authentication

All endpoints require PIN authentication or API Key authentication.

---

## GET /api/settings/schema

Retrieve the full settings schema definition. Returns key names, types, defaults, categories, and other metadata for all settings.

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | Setting key (dot-separated, e.g. `github.token`) |
| `type` | string | Value type (`str`, `int`, `float`, `bool`) |
| `default` | any | Default value |
| `category` | string | Category name |
| `secret` | bool | Whether this is a secret value |
| `label` | string | Display label |

---

## GET /api/settings/all

Retrieve all setting values. Secret values are returned in masked form.

### Parameters

None

### Response

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

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | Setting key |
| `value` | any | Current value (masked if secret) |
| `source` | string | Value source: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Whether this is a secret value |
| `category` | string | Category name |

---

## GET /api/settings/\<key\>

Retrieve a single setting value. The key uses dot-separated path format (e.g. `github.token`).

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Setting key (path parameter) |

### Response

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Unknown setting key |

---

## PUT /api/settings/\<key\>

Update a setting value. Secret values are automatically encrypted. Optionally specify a 1Password URI to manage the secret externally.

### Rate Limit

DESTRUCTIVE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Setting key (path parameter) |

### Request

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `value` | any | Yes | The value to set. Automatically coerced to the schema-defined type |
| `op_uri` | string | No | 1Password URI. When specified, saves an `op_secrets` mapping instead of the value |

### Response

```json
{
  "key": "github.token",
  "updated": true
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Request body missing `value` |
| 404 | `not_found` | Unknown setting key |

---

## GET /api/settings/secrets/status

Retrieve the encryption key backend status. Shows which key management method is currently in use.

### Parameters

None

### Response

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `backend` | string | Current key backend (`keychain` / `passphrase` / `file`) |
| `available` | bool | Whether encryption is available |
| `keychain_supported` | bool | Whether OS keychain is supported |

---

## POST /api/settings/secrets/export

Export the encryption key as password-protected JSON. Used for backup or migration to another environment.

### Rate Limit

DESTRUCTIVE

### Request

```json
{
  "password": "my-export-password"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `password` | string | Yes | Password to protect the exported data |

### Response

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Request body missing `password` |
| 400 | `export_failed` | Export operation failed |

---

## POST /api/settings/secrets/import

Import an encryption key from previously exported data.

### Rate Limit

DESTRUCTIVE

### Request

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `export_data` | string | Yes | The data obtained during export |
| `password` | string | Yes | The password set during export |

### Response

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Missing `export_data` or `password` |
| 400 | `import_failed` | Wrong password or corrupted data |

---

## POST /api/settings/secrets/migrate-keychain

Migrate the encryption key from file backend to OS keychain. Supports macOS Keychain, Windows Credential Manager, and Linux Secret Service.

### Rate Limit

DESTRUCTIVE

### Request

None (no body required)

### Response

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `migration_failed` | Keychain unavailable or migration failed |

---

## GET /api/settings/op-status

Retrieve 1Password CLI (`op`) connection status.

### Parameters

None

### Response

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `available` | bool | Whether `op` command exists on PATH |
| `signed_in` | bool | Whether signed in to 1Password |
| `version` | string | `op` CLI version |

---

## GET /api/settings/secrets/op-vaults

List available 1Password vaults.

### Parameters

None

### Response

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

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI not available |

---

## POST /api/settings/secrets/push-to-op

Batch-write all secret settings to 1Password and save `op_secrets` mappings in config.json.

### Rate Limit

DESTRUCTIVE

### Request

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `vault` | string | Yes | Target 1Password vault name |
| `item_title` | string | No | 1Password item title. Default: `YU AI Manager` |
| `remove_local` | bool | No | If `true`, removes locally encrypted values from config.json after push. Default: `false` |

### Response

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

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `bad_request` | Missing `vault` |
| 400 | `no_secrets` | No secrets to push |
| 500 | `op_push_failed` | Failed to write to 1Password |
| 503 | `op_unavailable` | 1Password CLI not available |

---

## DELETE /api/settings/op-mapping/\<key\>

Remove a 1Password URI mapping, reverting to local encryption.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Setting key (path parameter) |

### Response

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Key not found in `op_secrets` mapping |

---

## GET /api/settings/bw-status

Retrieve Bitwarden CLI (`bw`) connection status.

### Parameters

None

### Response

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `available` | bool | Whether `bw` command exists on PATH |
| `status` | string | Bitwarden session status |

---

## GET /api/settings/secrets/bw-folders

List available Bitwarden folders.

### Parameters

None

### Response

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

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI not available |

---

## POST /api/settings/secrets/push-to-bw

Batch-write all secret settings to Bitwarden and save `bw_secrets` mappings in config.json.

### Rate Limit

WRITE

### Request

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `folder_id` | string/null | No | Target Bitwarden folder ID. Omit for no folder |
| `item_name` | string | No | Bitwarden item name. Default: `YU AI Manager` |

### Response

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

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | `no_secrets` | No secrets to push |
| 500 | `bw_push_failed` | Failed to write to Bitwarden |
| 503 | `bw_unavailable` | Bitwarden CLI not available |

---

## DELETE /api/settings/bw-mapping/\<key\>

Remove a Bitwarden mapping, reverting to local encryption.

### Rate Limit

WRITE

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | string | Setting key (path parameter) |

### Response

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 404 | `not_found` | Key not found in `bw_secrets` mapping |
