# API de Claves API

APIs para crear, listar y eliminar claves API. Todos los endpoints requieren autenticación de sesión PIN.

Las claves API se generan en el formato `sk_` + 32 caracteres hexadecimales (128 bits). Solo se almacena el hash en el servidor; la clave sin procesar se devuelve solo una vez en el momento de la creación.

## Alcances

Las claves API se pueden asignar a alcances para restringir qué endpoints pueden acceder. Las claves sin alcances se establecen por defecto en acceso de solo lectura.

| Alcance | Descripción |
|-------|-------------|
| `read` | Búsqueda, detalles de archivo, miniaturas, estadísticas |
| `rate` | Obtener/establecer/lotes de calificaciones |
| `tag.write` | Agregar/eliminar etiqueta |
| `collection.write` | Crear/actualizar/eliminar colección, agregar por lotes, favoritos |
| `annotate` | Leer/escribir/eliminar anotación |
| `scan` | Iniciar/cancelar/reanudar escaneo |
| `admin` | Gestión de claves API, configuración, copia de seguridad/restauración |

## POST /api/apikeys

Crear una nueva clave API.

### Limitación de Velocidad

WRITE (alcance: `admin`)

### Autenticación

Sesión PIN o clave API con alcance `admin`

### Solicitud

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `label` | string | No | Etiqueta identificadora para la clave. Predeterminado es `Key <timestamp>` si se omite |
| `scopes` | string[] | No | Array de alcances. Omitir o pasar array vacío para acceso de solo lectura |

### Respuesta (201)

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

> **Nota**: El campo `key` solo se incluye en la respuesta de creación. Este valor no se puede recuperar nuevamente, así que guárdelo en una ubicación segura.

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Alcance especificado inválido |

## GET /api/apikeys

Listar todas las claves API. Los hashes no se incluyen; solo se devuelve el prefijo.

### Autenticación

Sesión PIN o clave API con alcance `admin`

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | string | ID de clave (`ak_` prefijo) |
| `key_prefix` | string | Primeros 10 caracteres de la clave (para identificación) |
| `label` | string | Etiqueta definida por el usuario |
| `created_at` | int | Hora de creación (marca de tiempo Unix) |
| `last_used_at` | int/null | Última hora de uso. `null` si nunca se ha usado |
| `scopes` | string[] | Alcances asignados. Campo omitido si no se establecen alcances |

## DELETE /api/apikeys/<key_id>

Eliminar (revocar) una clave API.

### Limitación de Velocidad

WRITE (alcance: `admin`)

### Autenticación

Sesión PIN o clave API con alcance `admin`

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `key_id` | string | ID de clave API (parámetro de ruta) |

### Respuesta

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 404 | Clave con el ID especificado no encontrada |

## Usando Claves API

Use la clave API creada a través del encabezado `Authorization`:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Las solicitudes autenticadas con claves API no requieren el encabezado CSRF (`X-Requested-With`).
