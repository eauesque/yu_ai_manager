# API Profils

APIs for managing configuration profiles. Profiles are named snapshots of application paramètres, stored as `profiles/<name>.json`.

All endpoints require PIN authentication. Returns 403 if PIN auth is disabled, or 401 if the session is not authenticated.

## Profile Name Rules

- 1 to 64 characters
- Allowed characters: `a-zA-Z0-9_-`

---

## GET /api/profiles

List metadata for all profiles. Sorted by favorites first, then alphabetically by label.

### Paramètres

None

### Réponse

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

| Champ | Type | Description |
|-------|------|-------------|
| `name` | string | Profile name (used as filename) |
| `label` | string | Display label |
| `description` | string | Description text |
| `favorite` | boolean | Favorite flag |
| `last_used_at` | string/null | Last used timestamp (ISO 8601) |
| `created_at` | string/null | Creation timestamp (ISO 8601) |
| `db` | string/null | Associated database path |
| `is_active` | boolean | Si this is the currently active profile |

## GET /api/profiles/\<name\>

Get the full data of a specific profile.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Profile name (path parameter) |

### Réponse

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Invalid profile name |
| `profile_not_found` | 404 | Profile does not exist |

## POST /api/profiles

Créer un nouveau profile.

### Rate Limit

WRITE

### Requête

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Profile name (`a-zA-Z0-9_-`, 1-64 chars) |
| `label` | string | No | Display label. Défauts to `name` if omitted |
| `description` | string | No | Description text |
| `base_config` | object | No | Initial configuration values. Keys other than metadata keys (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) are copied into the profile |

### Réponse (201)

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Invalid profile name |
| `invalid_label` | 400 | Label is empty |
| `profile_exists` | 409 | A profile with the same name already exists |

## PUT /api/profiles/\<name\>

Update profile metadata. Only `label`, `description`, and `favorite` can be changed.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Profile name (path parameter) |

### Requête

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `label` | string | No | Display label |
| `description` | string | No | Description text |
| `favorite` | boolean | No | Favorite flag |

At least one field must be provided.

### Réponse

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `empty_update` | 400 | No fields specified for update |
| `update_failed` | 400 | Profile not found, etc. |

## DELETE /api/profiles/\<name\>

Delete a profile. The currently active profile cannot be deleted.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Profile name (path parameter) |

### Réponse

```json
{
  "deleted": "my_profile"
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `delete_active` | 400 | Cannot delete the active profile |
| `delete_failed` | 400 | Profile not found, etc. |

## POST /api/profiles/\<name\>/duplicate

Duplicate a profile with a new name.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Source profile name (path parameter) |

### Requête

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | New profile name |
| `new_label` | string | No | New display label. Défauts to `new_name` if omitted |

### Réponse (201)

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `duplicate_failed` | 400 | Source not found, invalid new name, or name already exists |

## POST /api/profiles/\<name\>/rename

Rename a profile. If the active profile is renamed, `active_profile` in `config.json` is automatically updated.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Current profile name (path parameter) |

### Requête

```json
{
  "new_name": "renamed_profile"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | New profile name |

### Réponse

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Invalid new profile name |
| `rename_failed` | 400 | Source profile not found or new name already exists |

## POST /api/profiles/\<name\>/favorite

Toggle a profile's favorite status. Inverts the current `favorite` value.

### Rate Limit

WRITE

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Profile name (path parameter) |

### Requête

No body required.

### Réponse

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `profile_not_found` | 404 | Profile does not exist |
| `favorite_failed` | 400 | Update failed |

---

## QR Export / Import

Export and import profiles as JSON strings for QR codes. Sensitive fields (containing `pin`, `token`, `secret`, or `key`) are automatically stripped during export.

## GET /api/profiles/\<name\>/export

Export a profile as a QR-ready JSON string. Sensitive fields are excluded.

### Paramètres

| Paramètre | Type | Description |
|-----------|------|-------------|
| `name` | string | Profile name (path parameter) |

### Réponse

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` is a JSON string intended for embedding in a QR code. The `schema` field identifies the format version.

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `profile_not_found` | 404 | Profile does not exist |

## POST /api/profiles/import-preview

Preview an import from QR data. Used for checking differences with existing profiles. No actual import is performed.

### Rate Limit

WRITE

### Requête

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | JSON string or parsed object from QR code |

### Réponse (new profile)

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

### Réponse (existing profile)

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

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_qr` | 400 | Invalid QR data or missing `profile` key |
| `invalid_profile_name` | 400 | Invalid profile name |

## POST /api/profiles/import

Import a profile from QR data. Supports three modes: create new, diff merge, and full overwrite.

### Rate Limit

WRITE

### Requête

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| Paramètre | Type | Requis | Description |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | JSON string or parsed object from QR code |
| `mode` | string | No | Import mode: `full` (complete overwrite, default), `diff` (merge changed keys only), `new` (create new only) |

### Réponse

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

Returns status 201 when creating a new profile.

### Erreurs

| Code | Status | Description |
|------|--------|-------------|
| `invalid_qr` | 400 | Invalid QR data |
| `invalid_profile_name` | 400 | Invalid profile name |
| `profile_exists` | 409 | Profile already exists when `mode=new` |
| `import_failed` | 400 | Import failed |
