# API de Extensiones

APIs para gestionar extensiones, instalación, seguridad y autoría.

---

## GET /api/extensions

Lista todas las extensiones instaladas.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `extensions` | array | Array con información de extensiones |
| `total` | int | Número total de extensiones |
| `category_order` | string[] | Orden de visualización de categorías |

## GET /api/extensions/\<name\>

Obtiene información detallada sobre una extensión específica.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

### Errores

- `404` — Extensión no encontrada

## POST /api/extensions/\<name\>/toggle

Alterna el estado habilitado/deshabilitado de una extensión.

### Límite de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Solicitud

```json
{
  "enabled": true
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `enabled` | boolean | No | `true` para habilitar, `false` para deshabilitar. Omitir para alternar (invertir estado actual) |

### Respuesta

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Errores

- `404` — Extensión no encontrada

## GET /api/extensions/\<name\>/config

Obtiene el esquema de configuración y valores actuales de una extensión.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

### Errores

- `404` — Extensión no encontrada

## POST /api/extensions/\<name\>/config

Guarda valores de configuración de extensión. Incluye validación.

### Límite de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Solicitud

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `values` | object | Sí | Mapa de claves de campo a valores |

### Respuesta

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Errores

- `404` — Extensión no encontrada
- `400` — Error de validación

---

## Instalación / Actualización / Desinstalación de Extensiones

Los siguientes endpoints están restringidos a **acceso solo desde localhost**. Las solicitudes remotas devuelven `403`.

## POST /api/extensions/install

Instala una extensión desde un repositorio Git.

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Solicitud

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `url` | string | Sí | URL del repositorio Git. `git` y `repo` se aceptan como alias |

### Respuesta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Errores

- `400` — URL no proporcionada o formato de URL inválido
- `403` — Acceso desde fuera de localhost

## POST /api/extensions/\<name\>/update

Actualiza una extensión específica a la versión más reciente (git pull).

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Errores

- `403` — Acceso desde fuera de localhost
- `404` — Extensión no encontrada

## POST /api/extensions/update-all

Actualización por lotes de todas las extensiones instaladas desde Git.

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Respuesta

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Errores

- `403` — Acceso desde fuera de localhost

## DELETE /api/extensions/\<name\>/uninstall

Desinstala una extensión (elimina directorio).

### Límite de Velocidad

DESTRUCTIVE

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Errores

- `403` — Acceso desde fuera de localhost
- `404` — Extensión no encontrada

---

## Seguridad y Permisos

## GET /api/extensions/\<name\>/permissions

Obtiene información de permisos y estado de aprobación de una extensión.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `trust_level` | string | Nivel de confianza (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Si el usuario ha aprobado esta extensión |
| `permissions.required` | array | Lista de permisos requeridos |
| `permissions.optional` | array | Lista de permisos opcionales |
| `granted` | object/null | Detalles de permisos otorgados. `null` si no está aprobado aún |

### Errores

- `404` — Extensión no encontrada

## POST /api/extensions/\<name\>/permissions

Aprueba o revoca permisos de extensión.

### Límite de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Solicitud (Aprobar)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Solicitud (Revocar)

```json
{
  "action": "revoke"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `action` | string | No | `"approve"` (default) o `"revoke"` |
| `granted` | string[] | No | Lista de nombres de permisos a otorgar (para aprobar) |
| `denied` | string[] | No | Lista de nombres de permisos a denegar (para aprobar) |

### Respuesta (Aprobar)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Respuesta (Revocar)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Errores

- `400` — `granted` no es una lista
- `404` — Extensión no encontrada

## GET /api/extensions/\<name\>/scan-results

Obtiene resultados de análisis estático del código de extensión. Devuelve resultados tanto de ManifestAuthority como de CodeVerifier.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Si el manifest pasó revisión |
| `manifest_review.issues` | array | Lista de problemas (`severity`, `message`) |
| `code_scan` | object/null | Resultados del escaneo de código. `null` si no hay directorio |
| `code_scan.findings` | array | Lista de hallazgos |

### Errores

- `404` — Extensión no encontrada

## POST /api/extensions/\<name\>/rescan

Reescaneamos código de extensión. Devuelve el mismo formato de resultado que `scan-results`.

### Límite de Velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

Mismo formato que `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Obtiene el estado de emisión de token de capacidad para una extensión.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

### Errores

- `404` — Extensión no encontrada

## GET /api/extensions/\<name\>/integrity

Obtiene el estado de integridad de archivos de una extensión. También incluye información del rastreador de revocación y guarda de importación.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de la extensión (parámetro de ruta) |

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `integrity` | object | Resultados de verificación de integridad de archivos |
| `revocation` | object | Información del rastreador de revocación de token |
| `import_guard` | object | Recuento de denegar de guarda de importación |

### Errores

- `404` — Extensión no encontrada

---

## Hooks y Marketplace

## GET /api/extensions/hooks

Lista hooks de extensión registrados y definiciones de hooks.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `hooks` | object | Mapa de nombres de hooks a listas de extensiones registradas |
| `definitions` | object | Definiciones de hooks disponibles. `mode` es el modo de ejecución |

## GET /api/extensions/marketplace

Busca extensiones del marketplace.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `q` | string | No | Consulta de búsqueda (parámetro de query). La cadena vacía devuelve todas |

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `extensions` | array | Información de extensión del marketplace |
| `extensions[].installed` | boolean | Si la extensión está instalada localmente |
| `total` | int | Número total de resultados de búsqueda |

## POST /api/extensions/marketplace/refresh

Fuerza la actualización del caché del marketplace.

### Límite de Velocidad

WRITE

### Respuesta

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## Aislamiento

## GET /api/extensions/isolation

Obtiene el estado del aislamiento de proceso.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `available` | boolean | Si el aislamiento de proceso está disponible |
| `processes` | object | Mapa de nombres de extensiones a estado de proceso |

## GET /api/extensions/os-isolation

Obtiene el estado del aislamiento a nivel de SO (Fase D). También incluye información de aislamiento de proceso.

### Parámetros

Ninguno

### Respuesta

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `os_isolation` | object | Información de aislamiento a nivel de SO |
| `config.enabled` | boolean | Si el aislamiento a nivel de SO está habilitado |
| `config.apparmor` | boolean | Estado de uso de AppArmor (Linux) |
| `config.macos_sandbox_exec` | boolean | Estado de uso de sandbox-exec de macOS |
| `config.macos_user_isolation` | boolean | Estado de aislamiento de usuario de macOS |
| `config.windows_restricted_token` | boolean | Estado de uso de token restringido de Windows |
| `config.windows_job_object` | boolean | Estado de uso de Job Object de Windows |
| `processes` | object | Estado de aislamiento de proceso |

---

## Autoría de Extensiones

APIs para crear y editar extensiones personalizadas. Basado en el modelo de concesión, solo el directorio `extensions/custom-{name}/` es escribible.

Todos los endpoints están restringidos a **acceso solo desde localhost**.

### Restricciones de Seguridad

- Nombre de extensión: alfanumérico minúscula e guiones solamente (`[a-z0-9-]`), máximo 50 caracteres, prefijo `builtin-` prohibido
- Tipos de archivo: solo lista blanca (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- Archivos binarios: completamente prohibidos
- Límites de tamaño de archivo: 10KB a 50KB según tipo

## POST /api/extensions/author/create

Crea una nueva extensión personalizada con archivos de andamio.

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Solicitud

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `name` | string | Sí | Nombre de extensión (`[a-z0-9-]`, máximo 50 caracteres) |
| `description` | string | No | Descripción de extensión |

### Respuesta

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

### Errores

- `400` — Nombre inválido o extensión ya existe
- `403` — Acceso desde fuera de localhost

## POST /api/extensions/author/\<name\>/write

Escribe un archivo en una extensión personalizada.

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de extensión (parámetro de ruta, sin prefijo `custom-`) |

### Solicitud

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_type` | string | Sí | Tipo de archivo. Uno de: `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` |
| `filename` | string | Sí | Nombre de archivo sin extensión. Alfanumérico, guiones y guiones bajos solamente |
| `content` | string | Sí | Contenido del archivo (solo texto) |

### Restricciones de Tipo de Archivo

| file_type | Extensión | Tamaño Máx | Notas |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Punto de entrada de extensión |
| `template` | `.html` | 50KB | Colocado en `templates/{name}/` |
| `static_css` | `.css` | 50KB | Colocado en `static/` |
| `static_js` | `.js` | 50KB | Colocado en `static/` |
| `config` | `.json` | 10KB | El nombre del archivo debe ser `extension` |
| `readme` | `.md` | 20KB | El nombre del archivo debe ser `README` |

### Respuesta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Errores

- `400` — Error de validación (nombre inválido, tipo de archivo, tamaño excedido, binario detectado)
- `403` — Acceso desde fuera de localhost

## GET /api/extensions/author/\<name\>/read

Lee un archivo de una extensión personalizada.

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de extensión (parámetro de ruta) |

### Parámetros de Query

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_type` | string | Sí | Tipo de archivo |
| `filename` | string | Sí | Nombre de archivo sin extensión |

### Respuesta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Errores

- `400` — Error de validación
- `403` — Acceso desde fuera de localhost

## GET /api/extensions/author/\<name\>/files

Lista todos los archivos en una extensión personalizada.

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de extensión (parámetro de ruta) |

### Respuesta

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

### Errores

- `400` — Nombre de extensión inválido
- `403` — Acceso desde fuera de localhost

## POST /api/extensions/author/\<name\>/validate

Valida extension.json y código de una extensión personalizada. Ejecuta CodeVerifier sin registrar la extensión.

### Límite de Velocidad

WRITE

### Restricción de Acceso

Solo localhost

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | string | Nombre de extensión (parámetro de ruta) |

### Respuesta (Éxito)

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

### Respuesta (Problemas Encontrados)

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

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | boolean | Si todas las verificaciones pasaron |
| `issues` | string[] | Problemas de verificación de manifest y código |
| `code_findings` | array | Hallazgos de CodeVerifier |
| `manifest` | object | Contenido parseado de extension.json |

### Errores

- `400` — Nombre de extensión inválido o extensión no existe
- `403` — Acceso desde fuera de localhost
