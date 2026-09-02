# API de Actualización del Sistema

API para verificar nuevas versiones en GitHub y aplicar actualizaciones de aplicación.
Detecta automáticamente el tipo de instalación (git / tauri / docker / portable) y proporciona el método de actualización apropiado.

## GET /api/system/update/check

Verificar si hay una nueva versión disponible en el repositorio de GitHub.

- **Límite de velocidad**: Ninguno (GET)
- **Autenticación**: Sesión PIN o API Key

### Respuesta

```json
{
  "current": "4.21.0",
  "latest": "4.22.0",
  "update_available": true,
  "release_url": "https://github.com/...",
  "release_notes": "## What's New\n...",
  "published_at": "2026-03-20T12:00:00Z",
  "install_type": "git",
  "docker_command": null,
  "portable_download_url": null
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `current` | string | Versión actual |
| `latest` | string | Última versión en GitHub |
| `update_available` | bool | Si una nueva versión está disponible |
| `release_url` | string | URL de página de lanzamiento de GitHub |
| `release_notes` | string | Notas de lanzamiento (Markdown) |
| `published_at` | string | Fecha de publicación del lanzamiento (ISO 8601) |
| `install_type` | string | Tipo de instalación (`"git"`, `"tauri"`, `"docker"`, `"portable"`) |
| `docker_command` | string \| null | Solo Docker: comando para actualizar |
| `portable_download_url` | string \| null | Solo Portable: URL de descarga |

---

## GET /api/system/update/status

Obtener información sobre el tipo de instalación actual y la información de versión.

- **Límite de velocidad**: Ninguno (GET)
- **Autenticación**: Sesión PIN o API Key

### Respuesta

```json
{
  "version": "4.21.0",
  "install_type": "git",
  "update_in_progress": false
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `version` | string | Versión actual |
| `install_type` | string | Tipo de instalación (`"git"` \| `"tauri"` \| `"docker"` \| `"portable"`) |
| `update_in_progress` | bool | Si una actualización está en progreso |

---

## POST /api/system/update/apply

Aplicar una actualización disponible. Solo soportado para instalaciones de clones git y portátiles.

- **Límite de velocidad**: DESTRUCTIVE
- **Autenticación**: Sesión PIN (localhost) o token de reinicio
- **CSRF**: Se requiere `X-Requested-With: XMLHttpRequest`

### Cuerpo de Solicitud

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `confirm` | string | Sí | Cadena de confirmación. Debe ser `"update"` |

### Ejemplo de Solicitud

```json
{
  "confirm": "update"
}
```

### Respuesta

```json
{
  "ok": true,
  "message": "Update started"
}
```

### Eventos SSE

Durante la actualización, los eventos `update.progress` se entregan a través de SSE.

```
event: update.progress
data: {"step": "backup", "status": "running", "detail": "Creating backup..."}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `step` | string | Paso de progreso (ver más abajo) |
| `status` | string | `"running"` \| `"done"` \| `"error"` |
| `detail` | string | Detalles del paso |

#### Referencia de Pasos

| Paso | Descripción |
|------|-------------|
| `backup` | Crear una copia de seguridad |
| `fetch` | Ejecutar git fetch |
| `pull` | Ejecutar git pull |
| `download` | Descargar archivos (portable) |
| `extract` | Extraer archivo (portable) |
| `replace` | Reemplazar archivos (portable) |
| `pip_install` | Instalar dependencias de Python |
| `ts_build` | Compilar TypeScript |
| `complete` | Actualización completada |

### Respuestas de Error

**Instalaciones Docker** (400):
```json
{
  "ok": false,
  "error": "Docker installs cannot be updated from the web UI. Pull the latest image instead.",
  "code": "DOCKER_UPDATE_NOT_SUPPORTED"
}
```

**Instalaciones Tauri** (400):
```json
{
  "ok": false,
  "error": "Tauri updates are handled by the desktop app's built-in updater.",
  "code": "TAURI_UPDATE_NOT_SUPPORTED"
}
```

---

## Notas

- Las instalaciones Docker no pueden usar `/api/system/update/apply`. Utilice `docker pull` para obtener la imagen más reciente
- Las actualizaciones de la aplicación de escritorio Tauri se manejan mediante el actualizador integrado de la aplicación
- Solo las instalaciones git y portátiles admiten actualizaciones a través de la WebUI
- Es posible que ocurra un reinicio del servidor durante el proceso de actualización

---

## GET /api/system/update/unified-check

Verificar el estado de actualización del sistema y todas las extensiones a la vez.

- **Límite de velocidad**: Ninguno (GET)
- **Autenticación**: Sesión PIN o API Key

### Parámetros de Consulta

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `force` | string | `"1"` para omitir caché y re-verificar |

### Respuesta

```json
{
  "system": {
    "current": "4.22.0",
    "latest": "4.23.0",
    "update_available": true,
    "install_type": "git"
  },
  "extensions": [
    {
      "name": "builtin-backup",
      "version": "1.0.0",
      "source": "builtin",
      "status": "builtin",
      "enabled": true,
      "description": "..."
    },
    {
      "name": "my-custom-ext",
      "version": "0.3.0",
      "source": "git",
      "status": "update_available",
      "enabled": true,
      "description": "...",
      "local_head": "abc12345",
      "remote_head": "def67890",
      "commits_behind": 3
    }
  ],
  "summary": {
    "total": 45,
    "up_to_date": 1,
    "update_available": 1,
    "unknown": 0,
    "builtin": 43
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `system` | object | Información de actualización del sistema (mismo formato que `check_for_update`) |
| `extensions` | array | Estado de actualización por extensión |
| `extensions[].status` | string | `"up_to_date"` \| `"update_available"` \| `"unknown"` \| `"builtin"` |
| `extensions[].source` | string | `"builtin"` \| `"git"` \| `"local"` |
| `extensions[].commits_behind` | int | Número de commits detrás del remoto (cuando hay actualización disponible) |
| `summary` | object | Desglose de conteo por categoría |

---

## POST /api/system/update/unified-apply

Aplicar actualizaciones del sistema y/o extensiones en una sola operación. Las configuraciones de extensión se respaldan automáticamente antes de actualizar.

- **Límite de velocidad**: DESTRUCTIVE
- **Autenticación**: Sesión PIN (localhost) o token de reinicio
- **CSRF**: Se requiere `X-Requested-With: XMLHttpRequest`

### Cuerpo de Solicitud

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `update_system` | bool | No | Actualizar el sistema (por defecto: true) |
| `update_extensions` | bool | No | Actualizar extensiones (por defecto: true) |
| `extension_names` | array | No | Lista de nombres de extensión a actualizar (omitir para todas las extensiones git) |

### Ejemplo de Solicitud

```json
{
  "update_system": true,
  "update_extensions": true,
  "extension_names": ["my-custom-ext"]
}
```

### Respuesta

```json
{
  "ok": true,
  "accepted": true,
  "message": "Unified update started. Progress via SSE (update.progress).",
  "update_system": true,
  "update_extensions": true
}
```

### Eventos SSE

Durante actualizaciones unificadas, los eventos `update.progress` incluyen la bandera `"unified": true`.

```
event: update.progress
data: {"step": "ext_config_backup", "status": "done", "detail": "...", "unified": true}
event: update.progress
data: {"step": "ext_update_my-custom-ext", "status": "running", "detail": "(1/1)", "unified": true}
```

#### Pasos Adicionales

| Paso | Descripción |
|------|-------------|
| `ext_config_backup` | Copia de seguridad de configuración de extensión |
| `ext_update_<name>` | Actualización de extensión individual |

---

## Integración MCP

Gestionar actualizaciones del sistema desde Claude Desktop.

```
# Paso 1: Verificar nueva versión
check_for_update()

# Paso 2: Verificar estado de actualización
get_update_status()

# Paso 3: Aplicar actualización (solo git/portable)
apply_system_update(confirm="update")

# Verificación unificada: sistema + todas las extensiones
check_unified_updates()

# Aplicación unificada: actualizar sistema + extensiones a la vez
apply_unified_updates(update_system=True, update_extensions=True)
```

### Herramientas MCP

| Herramienta | Descripción |
|------|-------------|
| `check_for_update` | Verificar si hay una nueva versión disponible en GitHub |
| `get_update_status` | Obtener tipo de instalación actual y versión |
| `apply_system_update` | Aplicar actualización disponible (solo git/portable) |
| `check_unified_updates` | Verificar estado de actualización para sistema + todas las extensiones |
| `apply_unified_updates` | Actualizar sistema + extensiones a la vez (copia de seguridad automática de configuraciones) |
