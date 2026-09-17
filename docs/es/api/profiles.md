# API de Perfiles

APIs para gestionar perfiles de configuración. Los perfiles son instantáneas nombradas de la configuración de la aplicación, almacenadas como `profiles/<name>.json`.

Todos los endpoints requieren autenticación PIN. Devuelve 403 si la autenticación PIN está deshabilitada, o 401 si la sesión no está autenticada.

## Reglas de Nombre de Perfil

- 1 a 64 caracteres
- Caracteres permitidos: `a-zA-Z0-9_-`

---

## GET /api/profiles

Listar metadatos para todos los perfiles. Ordenados por favoritos primero, luego alfabéticamente por etiqueta.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Nombre del perfil (usado como nombre de archivo) |
| `label` | string | Etiqueta mostrada |
| `description` | string | Texto de descripción |
| `favorite` | boolean | Bandera favorita |
| `last_used_at` | string/null | Timestamp de último uso (ISO 8601) |
| `created_at` | string/null | Timestamp de creación (ISO 8601) |
| `db` | string/null | Ruta de base de datos asociada |
| `is_active` | boolean | Si este es el perfil actualmente activo |

## GET /api/profiles/\<name\>

Obtener los datos completos de un perfil específico.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil (parámetro de ruta) |

### Respuesta

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_profile_name` | 400 | Nombre de perfil inválido |
| `profile_not_found` | 404 | El perfil no existe |

## POST /api/profiles

Crear un nuevo perfil.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `name` | string | Sí | Nombre del perfil (`a-zA-Z0-9_-`, 1-64 caracteres) |
| `label` | string | No | Etiqueta mostrada. Por defecto `name` si se omite |
| `description` | string | No | Texto de descripción |
| `base_config` | object | No | Valores de configuración iniciales. Las claves que no sean claves de metadatos (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) se copian al perfil |

### Respuesta (201)

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_profile_name` | 400 | Nombre de perfil inválido |
| `invalid_label` | 400 | La etiqueta está vacía |
| `profile_exists` | 409 | Un perfil con el mismo nombre ya existe |

## PUT /api/profiles/\<name\>

Actualizar metadatos del perfil. Solo se pueden cambiar `label`, `description` y `favorite`.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil (parámetro de ruta) |

### Solicitud

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `label` | string | No | Etiqueta mostrada |
| `description` | string | No | Texto de descripción |
| `favorite` | boolean | No | Bandera favorita |

Se debe proporcionar al menos un campo.

### Respuesta

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `empty_update` | 400 | Sin campos especificados para actualizar |
| `update_failed` | 400 | El perfil no se encontró, etc. |

## DELETE /api/profiles/\<name\>

Eliminar un perfil. El perfil actualmente activo no se puede eliminar.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil (parámetro de ruta) |

### Respuesta

```json
{
  "deleted": "my_profile"
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `delete_active` | 400 | No se puede eliminar el perfil activo |
| `delete_failed` | 400 | El perfil no se encontró, etc. |

## POST /api/profiles/\<name\>/duplicate

Duplicar un perfil con un nuevo nombre.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil de origen (parámetro de ruta) |

### Solicitud

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `new_name` | string | Sí | Nuevo nombre de perfil |
| `new_label` | string | No | Nueva etiqueta mostrada. Por defecto `new_name` si se omite |

### Respuesta (201)

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `duplicate_failed` | 400 | Origen no encontrado, nuevo nombre inválido o nombre ya existe |

## POST /api/profiles/\<name\>/rename

Renombrar un perfil. Si el perfil activo se renombra, `active_profile` en `config.json` se actualiza automáticamente.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre actual del perfil (parámetro de ruta) |

### Solicitud

```json
{
  "new_name": "renamed_profile"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `new_name` | string | Sí | Nuevo nombre de perfil |

### Respuesta

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_profile_name` | 400 | Nuevo nombre de perfil inválido |
| `rename_failed` | 400 | Perfil de origen no encontrado o nuevo nombre ya existe |

## POST /api/profiles/\<name\>/favorite

Alternar el estado favorito de un perfil. Invierte el valor `favorite` actual.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil (parámetro de ruta) |

### Solicitud

Sin cuerpo requerido.

### Respuesta

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `profile_not_found` | 404 | El perfil no existe |
| `favorite_failed` | 400 | La actualización falló |

---

## Exportación/Importación de QR

Exportar e importar perfiles como cadenas JSON para códigos QR. Los campos sensibles (que contienen `pin`, `token`, `secret` o `key`) se eliminan automáticamente durante la exportación.

## GET /api/profiles/\<name\>/export

Exportar un perfil como cadena JSON lista para QR. Los campos sensibles se excluyen.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre del perfil (parámetro de ruta) |

### Respuesta

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` es una cadena JSON destinada a incrustar en un código QR. El campo `schema` identifica la versión del formato.

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `profile_not_found` | 404 | El perfil no existe |

## POST /api/profiles/import-preview

Mostrar una vista previa de una importación desde datos QR. Se utiliza para verificar diferencias con perfiles existentes. No se realiza importación real.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Sí | Cadena JSON u objeto analizado del código QR |

### Respuesta (perfil nuevo)

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

### Respuesta (perfil existente)

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

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_qr` | 400 | Datos QR inválidos o clave `profile` faltante |
| `invalid_profile_name` | 400 | Nombre de perfil inválido |

## POST /api/profiles/import

Importar un perfil desde datos QR. Admite tres modos: crear nuevo, fusión diferencial y sobrescritura completa.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Sí | Cadena JSON u objeto analizado del código QR |
| `mode` | string | No | Modo de importación: `full` (sobrescritura completa, por defecto), `diff` (fusionar solo claves cambiadas), `new` (crear solo si es nuevo) |

### Respuesta

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

Devuelve estado 201 al crear un nuevo perfil.

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_qr` | 400 | Datos QR inválidos |
| `invalid_profile_name` | 400 | Nombre de perfil inválido |
| `profile_exists` | 409 | El perfil ya existe cuando `mode=new` |
| `import_failed` | 400 | La importación falló |
