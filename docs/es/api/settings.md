# API de Configuración

APIs para gestionar la configuración de aplicación, cifrado de secretos e integración de gestor de contraseñas externo (1Password / Bitwarden).

Los valores de secretos siempre se enmascaran (`****`) en respuestas GET. El campo `source` indica desde qué backend se resolvió el valor.

## Autenticación

Todos los endpoints requieren autenticación PIN o autenticación de Clave API.

---

## GET /api/settings/schema

Recuperar la definición del esquema de configuración completo. Devuelve nombres de clave, tipos, predeterminados, categorías y otros metadatos para todas las configuraciones.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `key` | string | Clave de configuración (separada por puntos, p. ej. `github.token`) |
| `type` | string | Tipo de valor (`str`, `int`, `float`, `bool`) |
| `default` | any | Valor predeterminado |
| `category` | string | Nombre de categoría |
| `secret` | bool | Si esto es un valor de secreto |
| `label` | string | Etiqueta de visualización |

---

## GET /api/settings/all

Recuperar todos los valores de configuración. Los valores de secreto se devuelven en forma enmascarada.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `key` | string | Clave de configuración |
| `value` | any | Valor actual (enmascarado si es secreto) |
| `source` | string | Origen del valor: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Si esto es un valor de secreto |
| `category` | string | Nombre de categoría |

---

## GET /api/settings/\<key\>

Recuperar un valor de configuración único. La clave usa formato de ruta separada por puntos (p. ej. `github.token`).

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key` | string | Clave de configuración (parámetro de ruta) |

### Respuesta

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 404 | `not_found` | Clave de configuración desconocida |

---

## PUT /api/settings/\<key\>

Actualizar un valor de configuración. Los valores de secreto se cifran automáticamente. Opcionalmente especificar un URI de 1Password para gestionar el secreto externamente.

### Limitación de Velocidad

DESTRUCTIVE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key` | string | Clave de configuración (parámetro de ruta) |

### Solicitud

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `value` | any | Sí | El valor a establecer. Se coerciona automáticamente al tipo definido en el esquema |
| `op_uri` | string | No | URI de 1Password. Cuando se especifica, guarda una asignación `op_secrets` en lugar del valor |

### Respuesta

```json
{
  "key": "github.token",
  "updated": true
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `bad_request` | Falta `value` en el cuerpo de la solicitud |
| 404 | `not_found` | Clave de configuración desconocida |

---

## GET /api/settings/secrets/status

Recuperar el estado del backend de clave de cifrado. Muestra qué método de gestión de claves se está utilizando actualmente.

### Parámetros

Ninguno

### Respuesta

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `backend` | string | Backend de clave actual (`keychain` / `passphrase` / `file`) |
| `available` | bool | Si el cifrado está disponible |
| `keychain_supported` | bool | Si se admite el llavero del sistema operativo |

---

## POST /api/settings/secrets/export

Exportar la clave de cifrado como JSON protegido por contraseña. Se utiliza para copia de seguridad o migración a otro entorno.

### Limitación de Velocidad

DESTRUCTIVE

### Solicitud

```json
{
  "password": "my-export-password"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `password` | string | Sí | Contraseña para proteger los datos exportados |

### Respuesta

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `bad_request` | Falta `password` en el cuerpo de la solicitud |
| 400 | `export_failed` | Falló la operación de exportación |

---

## POST /api/settings/secrets/import

Importar una clave de cifrado desde datos previamente exportados.

### Limitación de Velocidad

DESTRUCTIVE

### Solicitud

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `export_data` | string | Sí | Los datos obtenidos durante la exportación |
| `password` | string | Sí | La contraseña establecida durante la exportación |

### Respuesta

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `bad_request` | Falta `export_data` o `password` |
| 400 | `import_failed` | Contraseña incorrecta o datos corrupto |

---

## POST /api/settings/secrets/migrate-keychain

Migrar la clave de cifrado desde el backend de archivo al llavero del sistema operativo. Admite Keychain de macOS, Credential Manager de Windows y Secret Service de Linux.

### Limitación de Velocidad

DESTRUCTIVE

### Solicitud

Ninguno (sin cuerpo requerido)

### Respuesta

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `migration_failed` | Llavero no disponible o migración fallida |

---

## GET /api/settings/op-status

Recuperar estado de conexión de 1Password CLI (`op`).

### Parámetros

Ninguno

### Respuesta

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `available` | bool | Si el comando `op` existe en PATH |
| `signed_in` | bool | Si inició sesión en 1Password |
| `version` | string | Versión de CLI `op` |

---

## GET /api/settings/secrets/op-vaults

Listar bóvedas de 1Password disponibles.

### Parámetros

Ninguno

### Respuesta

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

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 503 | `op_unavailable` | 1Password CLI no disponible |

---

## POST /api/settings/secrets/push-to-op

Escribir por lotes todas las configuraciones secretas en 1Password y guardar asignaciones `op_secrets` en config.json.

### Limitación de Velocidad

DESTRUCTIVE

### Solicitud

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `vault` | string | Sí | Nombre de bóveda de 1Password objetivo |
| `item_title` | string | No | Título de elemento de 1Password. Predeterminado: `YU AI Manager` |
| `remove_local` | bool | No | Si `true`, elimina valores cifrados localmente de config.json después de push. Predeterminado: `false` |

### Respuesta

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

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `bad_request` | Falta `vault` |
| 400 | `no_secrets` | No hay secretos para push |
| 500 | `op_push_failed` | Falló escribir en 1Password |
| 503 | `op_unavailable` | 1Password CLI no disponible |

---

## DELETE /api/settings/op-mapping/\<key\>

Eliminar una asignación de URI de 1Password, revirtiendo al cifrado local.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key` | string | Clave de configuración (parámetro de ruta) |

### Respuesta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 404 | `not_found` | Clave no encontrada en asignación `op_secrets` |

---

## GET /api/settings/bw-status

Recuperar estado de conexión de Bitwarden CLI (`bw`).

### Parámetros

Ninguno

### Respuesta

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `available` | bool | Si el comando `bw` existe en PATH |
| `status` | string | Estado de sesión de Bitwarden |

---

## GET /api/settings/secrets/bw-folders

Listar carpetas de Bitwarden disponibles.

### Parámetros

Ninguno

### Respuesta

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

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 503 | `bw_unavailable` | Bitwarden CLI no disponible |

---

## POST /api/settings/secrets/push-to-bw

Escribir por lotes todas las configuraciones secretas en Bitwarden y guardar asignaciones `bw_secrets` en config.json.

### Limitación de Velocidad

WRITE

### Solicitud

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `folder_id` | string/null | No | ID de carpeta de Bitwarden objetivo. Omitir para sin carpeta |
| `item_name` | string | No | Nombre del elemento de Bitwarden. Predeterminado: `YU AI Manager` |

### Respuesta

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

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 400 | `no_secrets` | No hay secretos para push |
| 500 | `bw_push_failed` | Falló escribir en Bitwarden |
| 503 | `bw_unavailable` | Bitwarden CLI no disponible |

---

## DELETE /api/settings/bw-mapping/\<key\>

Eliminar una asignación de Bitwarden, revirtiendo al cifrado local.

### Limitación de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key` | string | Clave de configuración (parámetro de ruta) |

### Respuesta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errores

| Estado | Código | Descripción |
|--------|------|-------------|
| 404 | `not_found` | Clave no encontrada en asignación `bw_secrets` |
