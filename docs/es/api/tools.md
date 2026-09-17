# API de Herramientas

APIs de utilidad para detección de duplicados, cálculo de hash, búsqueda de imágenes similares, gestión de caché, selección de carpetas, copia de seguridad de BD, limpieza de archivos y registro de depuración.

---

## Duplicados / Hashes / Escaneo

### GET /api/tools/find-duplicates

Detectar archivos duplicados basándose en hash de archivo o nombre de archivo.

#### Límite de velocidad

HEAVY

#### Parámetros

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `cross_directory` | string | `"false"` | Establecer en `"true"` para detectar duplicados entre diferentes directorios |
| `method` | string | `"hash"` | Método de detección: `"hash"` o `"name"` |
| `threshold` | int | `5` | Umbral de similitud |

#### Respuesta

```json
{
  "groups": [
    {
      "hash": "abc123...",
      "files": [
        { "id": 1, "path": "/images/photo.png", "filename": "photo.png" },
        { "id": 2, "path": "/backup/photo.png", "filename": "photo.png" }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### POST /api/tools/compute-hashes

Iniciar cálculo de hash en segundo plano para archivos sin hashes.

#### Límite de velocidad

HEAVY

#### Solicitud

```json
{
  "type": "both",
  "limit": 5000
}
```

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `type` | string | `"both"` | Tipo de hash: `"md5"`, `"sha256"`, o `"both"` |
| `limit` | int | `5000` | Número máximo de archivos a procesar |

#### Respuesta

```json
{
  "started": true,
  "type": "both",
  "limit": 5000
}
```

### POST /api/tools/delete-duplicates

Eliminar archivos especificados de grupos de duplicados.

#### Límite de velocidad

DESTRUCTIVE

#### Solicitud

```json
{
  "groups": [
    {
      "keep": 1,
      "delete": [2, 3]
    }
  ],
  "mode": "soft"
}
```

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `groups` | array | Requerido | Objetivos de eliminación. `keep` = ID de archivo a mantener, `delete` = array de IDs de archivo a eliminar |
| `mode` | string | `"soft"` | `"soft"` = eliminación lógica, `"hard"` = eliminación física |

#### Respuesta

```json
{
  "deleted": 2,
  "errors": []
}
```

### GET /api/tools/normalize-tags

Normalizar etiquetas (fusionar duplicados, recortar espacios, etc.).

#### Parámetros

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `dry_run` | string | `"false"` | Establecer en `"true"` para vista previa de cambios sin aplicar |

#### Respuesta

```json
{
  "normalized": 15,
  "removed": 3,
  "dry_run": false
}
```

### GET /api/tools/find-similar

Encontrar imágenes similares a un archivo especificado (basado en hash).

#### Límite de velocidad

HEAVY

#### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo de referencia |
| `threshold` | int | No | Umbral de similitud (1-20, por defecto `5`) |

#### Respuesta

```json
{
  "file_id": 42,
  "threshold": 5,
  "results": [
    {
      "id": 43,
      "filename": "similar.png",
      "distance": 3
    }
  ],
  "count": 1
}
```

#### Errores

- `400` — `file_id` faltante o inválido
- `404` — Archivo especificado no encontrado

### POST /api/tools/scan

Escanear archivos en un directorio e registrarlos en la base de datos.

#### Límite de velocidad

HEAVY

#### Solicitud

```json
{
  "path": "/path/to/images",
  "recursive": true,
  "scan_zips": false,
  "compute_hash": false
}
```

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `path` | string | Requerido | Ruta de directorio a escanear |
| `recursive` | bool | `true` | Escanear subdirectorios recursivamente |
| `scan_zips` | bool | `false` | También escanear dentro de archivos ZIP |
| `compute_hash` | bool | `false` | Calcular hashes de archivo durante el escaneo |

#### Respuesta

```json
{
  "scanned": 150,
  "new": 42,
  "updated": 5,
  "errors": []
}
```

---

## Búsqueda de Archivos / Inspección de Metadatos

### GET /api/tools/file-search

Buscar archivos en la base de datos por palabra clave.

#### Parámetros

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `q` / `query` | string | `""` | Palabra clave de búsqueda |
| `meta` / `meta_filter` | string | `"all"` | Filtrar por fuente de metadatos (`"all"`, `"a1111_png"`, `"novelai_v4_png"`, etc.) |
| `limit` / `n` / `page_size` | int | `100` | Número de resultados (1-500) |

#### Respuesta

```json
{
  "results": [
    {
      "id": 1,
      "filename": "image.png",
      "path": "/images/image.png"
    }
  ],
  "count": 1
}
```

### POST /api/inspect

Inspeccionar metadatos de un archivo subido. Extrae metadatos sin registrar el archivo en la base de datos.

#### Límite de velocidad

WRITE

#### Solicitud

`multipart/form-data`:

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `file` | file | Sí | Archivo a inspeccionar |
| `zip_entry` | string | No | Ruta dentro del archivo ZIP (para archivos ZIP) |

#### Respuesta

```json
{
  "filename": "image.png",
  "meta_source": "novelai_v4_png",
  "positive": "1girl, landscape",
  "negative": "bad anatomy",
  "parameters": { ... }
}
```

#### Errores

- `400` — Ningún archivo subido

---

## Selección de Carpetas / Listado de Directorios

### GET /api/tools/select-folder

Abrir el diálogo nativo del selector de carpetas del SO. **Solo disponible desde localhost.**

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `initial` / `path` / `dir` | string | Directorio inicial para el diálogo |

#### Respuesta

```json
{
  "path": "C:\\Users\\user\\Pictures",
  "cancelled": false
}
```

Cuando se accede de forma remota:

```json
{
  "path": null,
  "error": "remote_client_no_gui",
  "cancelled": false,
  "message": "Native folder dialog is not available for remote access. Please use the server folder browser."
}
```

### GET /api/tools/list-dirs

Listar directorios en el servidor. **Solo disponible desde localhost.**

#### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` / `dir` / `initial` | string | Directorio a listar. Vacío devuelve directorios raíz |

#### Respuesta

```json
{
  "current": "C:\\Users",
  "parent": "C:\\",
  "dirs": ["user1", "Public"],
  "roots": ["C:\\", "D:\\"]
}
```

#### Errores

- `403` — Acceso remoto

---

## Gestión de Caché

### GET /api/tools/cache-info

Obtener estado de caché de miniaturas.

#### Respuesta

```json
{
  "count": 1234,
  "size_mb": 56.7
}
```

### POST /api/tools/clear-cache

Borrar todo el caché de miniaturas.

#### Límite de velocidad

DESTRUCTIVE

#### Respuesta

```json
{
  "cleared": 1234
}
```

### POST /api/tools/rebuild-groups

Forzar reconstrucción del caché de índice de grupos.

#### Límite de velocidad

DESTRUCTIVE

#### Respuesta

```json
{
  "status": "rebuilt",
  "folders": 42,
  "zips": 5,
  "file_count": 1500
}
```

### POST /api/tools/faststart-prescan

Pre-generar caché de inicio rápido para todos los archivos MP4/MOV en segundo plano. Devuelve 202 inmediatamente.

#### Límite de velocidad

WRITE

#### Respuesta (202)

```json
{
  "ok": true,
  "started": true,
  "message": "faststart prescan started"
}
```

Cuando ya está en ejecución (200):

```json
{
  "ok": true,
  "started": false,
  "message": "already running"
}
```

---

## Configuración

### GET /api/settings/config

Obtener la configuración actual fusionada con valores por defecto.

#### Respuesta

```json
{
  "port": 5000,
  "pin": "",
  "scan_roots": [],
  "theme": "dark",
  "backup": {
    "enabled": true,
    "periodic_interval_hours": 24
  }
}
```

### POST /api/settings/config

Actualizar parcialmente la configuración. Se aplica fusión profunda a objetos anidados existentes.

#### Límite de velocidad

DESTRUCTIVE

#### Solicitud

```json
{
  "theme": "light",
  "backup": {
    "enabled": false
  }
}
```

#### Respuesta

```json
{
  "status": "saved"
}
```

#### Errores

- `400` — Datos vacíos

---

## Copia de Seguridad / Restauración de BD

### GET /api/tools/backup-download

Descargar el archivo de base de datos directamente. **Solo disponible desde localhost.**

#### Respuesta

- Content-Type: `application/x-sqlite3`
- Content-Disposition: `attachment; filename="tags_backup_20260322_120000.db"`
- Devuelve 404 si la base de datos no se encuentra

### POST /api/tools/restore

Restaurar la base de datos subiendo un archivo `.db`. **Solo disponible desde localhost.** Crea automáticamente una copia de seguridad de la base de datos existente antes de restaurar.

#### Límite de velocidad

WRITE

#### Solicitud

`multipart/form-data`:

| Campo | Tipo | Requerido | Descripción |
|-------|------|----------|-------------|
| `file` | file | Sí | Archivo SQLite con extensión `.db` |

#### Validación

- Verifica bytes mágicos de SQLite
- Comprueba la tabla `files`
- Rechaza bases de datos que contienen triggers o vistas

#### Respuesta

```json
{
  "success": true,
  "message": "Database restored successfully",
  "backup": "tags.db.backup_1711100000"
}
```

#### Errores

- `400` — Ningún archivo subido, extensión incorrecta o SQLite inválido
- `403` — Acceso remoto
- `500` — Fallo de copia de seguridad o restauración

### POST /api/tools/backup/create

Crear manualmente una copia de seguridad administrada. **Solo disponible desde localhost.**

#### Límite de velocidad

DESTRUCTIVE

#### Respuesta

```json
{
  "success": true,
  "filename": "tags_backup_20260322_120000.db",
  "reason": "manual"
}
```

### GET /api/tools/backup/list

Listar copias de seguridad disponibles.

#### Respuesta

```json
{
  "backups": [
    {
      "filename": "tags_backup_20260322_120000.db",
      "size": 1048576,
      "created": "2026-03-22T12:00:00"
    }
  ],
  "count": 1
}
```

### POST /api/tools/backup/restore

Restaurar base de datos desde una copia de seguridad nombrada. **Solo disponible desde localhost.**

#### Límite de velocidad

DESTRUCTIVE

#### Solicitud

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `filename` | string | Sí | Nombre de archivo de copia de seguridad a restaurar |

#### Respuesta

```json
{
  "success": true,
  "message": "Backup restored",
  "filename": "tags_backup_20260322_120000.db"
}
```

#### Errores

- `400` — Nombre de archivo faltante o copia de seguridad no encontrada
- `403` — Acceso remoto

### POST /api/tools/backup/delete

Eliminar una copia de seguridad específica. **Solo disponible desde localhost.**

#### Límite de velocidad

DESTRUCTIVE

#### Solicitud

```json
{
  "filename": "tags_backup_20260322_120000.db"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `filename` | string | Sí | Nombre de archivo de copia de seguridad a eliminar |

#### Respuesta

```json
{
  "success": true,
  "deleted": "tags_backup_20260322_120000.db"
}
```

### GET /api/tools/backup/status

Obtener el estado del sistema de copia de seguridad.

#### Respuesta

```json
{
  "enabled": true,
  "backup_on_scan_complete": true,
  "periodic_interval_hours": 24,
  "max_generations": 5,
  "cooldown_minutes": 5,
  "scheduler_running": true,
  "last_backup_time": "2026-03-22T11:00:00",
  "within_cooldown": false
}
```

---

## Registro de Depuración

### GET /api/tools/debug-log

Obtener la cola del registro de depuración. Devuelve `enabled: false` cuando el modo de depuración está deshabilitado.

#### Parámetros

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `limit` | int | `200` | Número de líneas a recuperar (1-5000) |
| `filter` | string | `""` | Cadena de filtro de línea (coincidencia de subcadena) |

#### Respuesta

```json
{
  "enabled": true,
  "lines": ["2026-03-22 12:00:00 [INFO] Server started", "..."],
  "total_lines": 5000,
  "log_path": "/path/to/debug.log",
  "log_size_kb": 128.5
}
```

### GET /api/tools/debug-log/download

Descargar el archivo de registro de depuración. **Solo disponible desde localhost.**

#### Respuesta

- Content-Type: `text/plain`
- Content-Disposition: `attachment; filename="debug.log"`

#### Errores

- `400` — Modo de depuración no habilitado
- `403` — Acceso remoto
- `404` — Archivo de registro no encontrado

### POST /api/tools/debug-log/clear

Borrar el registro de depuración. **Solo disponible desde localhost.**

#### Límite de velocidad

WRITE

#### Respuesta

```json
{
  "success": true,
  "message": "Log cleared"
}
```

#### Errores

- `400` — Modo de depuración no habilitado
- `403` — Acceso remoto
- `404` — Archivo de registro no encontrado

---

## Limpieza de Archivos

Herramientas para detectar y limpiar archivos duplicados y sus carpetas extraídas. Todos los endpoints están **solo disponibles desde localhost.**

### POST /api/tools/archive-cleanup/scan

Escanear pares de archivos-carpetas.

#### Límite de velocidad

HEAVY

#### Solicitud

```json
{
  "path": "/path/to/check",
  "recursive": false
}
```

| Parámetro | Tipo | Por Defecto | Descripción |
|-----------|------|---------|-------------|
| `path` | string | Requerido | Directorio a escanear |
| `recursive` | bool | `false` | Escanear subdirectorios recursivamente |

#### Validación de Ruta

- Se rechazan rutas que comienzan con `~`
- Se rechazan rutas que contienen `..`

#### Respuesta

```json
{
  "pairs": [
    {
      "archive_path": "/data/images.zip",
      "folder_path": "/data/images",
      "archive_size": 10485760,
      "folder_size": 12582912,
      "file_count": 42
    }
  ],
  "count": 1
}
```

### POST /api/tools/archive-cleanup/execute

Ejecutar acciones de limpieza en pares escaneados.

#### Límite de velocidad

DESTRUCTIVE

#### Solicitud

```json
{
  "actions": [
    { "action": "delete_archive", "archive_path": "/data/images.zip" },
    { "action": "delete_folder", "folder_path": "/data/images" },
    { "action": "skip" }
  ]
}
```

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `actions` | array | Array de acciones |
| `actions[].action` | string | Uno de `"delete_archive"`, `"delete_folder"`, `"skip"` |
| `actions[].archive_path` | string | Requerido cuando la acción es `delete_archive` |
| `actions[].folder_path` | string | Requerido cuando la acción es `delete_folder` |

#### Respuesta

```json
{
  "results": [
    { "action": "delete_archive", "success": true },
    { "action": "delete_folder", "success": true },
    { "action": "skip", "success": true }
  ]
}
```

### POST /api/tools/archive-cleanup/llm-verify

Verificar identidad del par archivo-carpeta usando LLM (par único).

#### Límite de velocidad

HEAVY

#### Solicitud

```json
{
  "archive_path": "/data/images.zip",
  "folder_path": "/data/images",
  "pair_info": {
    "archive_size": 10485760,
    "folder_size": 12582912
  }
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `archive_path` | string | Sí | Ruta del archivo de archivo |
| `folder_path` | string | Sí | Ruta de carpeta extraída |
| `pair_info` | object | No | Metadatos adicionales de pareja |

#### Respuesta

```json
{
  "verdict": "same",
  "confidence": 0.95,
  "reasoning": "File counts and sizes match exactly."
}
```

### POST /api/tools/archive-cleanup/llm-verify-batch

Verificar lotes de múltiples pares usando LLM. Máximo 50 pares.

#### Límite de velocidad

HEAVY

#### Solicitud

```json
{
  "pairs": [
    {
      "archive_path": "/data/a.zip",
      "folder_path": "/data/a",
      "pair_info": {}
    }
  ]
}
```

| Parámetro | Tipo | Límite | Descripción |
|-----------|------|-------|-------------|
| `pairs` | array | Máx 50 | Array de pares a verificar |

#### Respuesta

```json
{
  "results": [
    { "result": { "verdict": "same", "confidence": 0.95, "reasoning": "..." } }
  ]
}
```

### GET /api/tools/archive-cleanup/llm-config

Obtener configuración LLM de limpieza de archivos.

#### Respuesta

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3",
  "api_key": ""
}
```

### POST /api/tools/archive-cleanup/llm-config

Guardar configuración LLM de limpieza de archivos.

#### Límite de velocidad

WRITE

#### Solicitud

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434",
  "model": "llama3"
}
```

#### Respuesta

```json
{
  "success": true
}
```

### POST /api/tools/archive-cleanup/list-models

Listar modelos disponibles para el motor especificado.

#### Solicitud

```json
{
  "engine": "ollama",
  "base_url": "http://localhost:11434"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `engine` | string | Sí | `"ollama"` o `"openai_compat"` |
| `base_url` | string | Sí | URL de API de motor |
| `api_key` | string | No | Clave de API para `openai_compat` |

#### Respuesta

```json
{
  "models": ["llama3", "mistral", "codellama"]
}
```

#### Errores

- `400` — Motor inválido o `base_url` faltante
