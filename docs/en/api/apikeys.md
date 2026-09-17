# API Keys API

APIs for creating, listing, and deleting API keys. All endpoints require PIN session authentication.

API keys are generated in the format `sk_` + 32 hex characters (128-bit). Only the hash is stored server-side; the raw key is returned only once at creation time.

## Scopes

API keys can be assigned scopes to restrict which endpoints they can access. Keys without scopes default to read-only access.

| Scope | Description |
|-------|-------------|
| `read` | Search, file details, thumbnails, stats |
| `rate` | Rating get/set/batch |
| `tag.write` | Tag add/remove |
| `collection.write` | Collection create/update/delete, batch-add, favorites |
| `annotate` | Annotation read/write/delete |
| `scan` | Scan start/cancel/resume |
| `admin` | API key management, settings, backup/restore |

## POST /api/apikeys

Create a new API key.

### Rate Limit

WRITE (scope: `admin`)

### Authentication

PIN session or API key with `admin` scope

### Request

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `label` | string | No | Identifying label for the key. Defaults to `Key <timestamp>` if omitted |
| `scopes` | string[] | No | Array of scopes. Omit or pass empty array for read-only access |

### Response (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **Note**: The `key` field is only included in the creation response. This value cannot be retrieved again, so store it in a secure location.

### Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid scope specified |

## GET /api/apikeys

List all API keys. Hashes are not included; only the prefix is returned.

### Authentication

PIN session or API key with `admin` scope

### Parameters

None

### Response

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Key ID (`ak_` prefix) |
| `key_prefix` | string | First 10 characters of the key (for identification) |
| `label` | string | User-defined label |
| `created_at` | int | Creation time (Unix timestamp) |
| `last_used_at` | int/null | Last usage time. `null` if never used |
| `scopes` | string[] | Assigned scopes. Field is omitted if no scopes are set |

## DELETE /api/apikeys/<key_id>

Delete (revoke) an API key.

### Rate Limit

WRITE (scope: `admin`)

### Authentication

PIN session or API key with `admin` scope

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `key_id` | string | API key ID (path parameter) |

### Response

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errors

| Status | Description |
|--------|-------------|
| 404 | Key with the specified ID not found |

## Using API Keys

Use the created API key via the `Authorization` header:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Requests authenticated with API keys do not require the CSRF header (`X-Requested-With`).
