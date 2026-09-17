# API de WD Tagger

APIs para WD Tagger (Waifu Diffusion Tagger) auto-etiquetado Danbooru. Proporciona gestión de configuración, etiquetado único/por lotes, CRUD de etiquetas, gestión de modelos, lectura de XMP y prueba de conexión de VLM.

## GET /api/wd-tagger/config

Obtener la configuración actual de WD Tagger.

### Parámetros

Ninguno

### Respuesta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Guardar/actualizar la configuración de WD Tagger.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| *(cualquier clave)* | any | No | Campo de configuración. Claves desconocidas o valores inválidos devuelven `400` |

### Respuesta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_json` | 400 | El cuerpo de la solicitud no es un objeto JSON |
| `invalid_value` | 400 | Valor de configuración inválido |

## POST /api/wd-tagger/tag/<file_id>

Ejecutar inferencia de WD Tagger en un archivo único para predecir y asignar etiquetas Danbooru.

### Límite de velocidad

HEAVY

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de archivo (parámetro de ruta) |

### Solicitud

```json
{
  "force": false
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `force` | boolean | No | Si es `true`, sobrescribir etiquetas existentes y volver a ejecutar la inferencia. Por defecto `false` |

### Respuesta

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `tag_error` | 400 | El etiquetado falló (archivo no encontrado, error al cargar imagen, etc.) |

## GET /api/wd-tagger/tags/<file_id>

Obtener etiquetas almacenadas de WD Tagger para un archivo específico.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `model` | string | No | Filtrar por nombre de modelo (parámetro de consulta) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### Respuesta

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Eliminar etiquetas de WD Tagger para un archivo específico.

### Límite de velocidad

WRITE

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `model` | string | No | Filtrar por nombre de modelo (parámetro de consulta). Si se omite, elimina etiquetas de todos los modelos |

### Respuesta

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Eliminar etiquetas de WD Tagger para múltiples archivos a la vez.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_ids` | list | Sí | Array de IDs de archivo (máx 500) |
| `model` | string | No | Filtrar por nombre de modelo. Si se omite, elimina etiquetas de todos los modelos |

### Respuesta

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Cuando el mismo archivo se reetiqueta con varios modelos de WD Tagger,
`file_wd_tags` conserva las etiquetas de cada modelo como historial. Al definir
un active model, la vista de detalle, la búsqueda `ai_analyzed` y la comprobación
interna de WD Tagger de "ya etiquetado" usan solo las etiquetas de ese modelo. Si
no hay active model, se conserva el comportamiento anterior y se usan juntas las
etiquetas de todos los modelos.

### Configuración en la UI

El retag modal muestra el `Active model` actual en la parte superior. Usa el
dropdown `Change` para seleccionar un modelo disponible. Elige `(none / reset)`
para borrar el active model.

Cuando termina un retag, el modelo usado pasa a ser active model por defecto.
Desmarca "Establecer como modelo activo tras reetiquetar" en el retag modal para
mantener el active model actual.

Las rows de modelos antiguos no se eliminan automáticamente. Permanecen en la
base de datos como historial. Para quitarlas explícitamente, activa "Eliminar
también etiquetas de otros modelos" en el retag modal y confirma el diálogo
después del retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Devuelve el active model actual y la lista de modelos presentes en la base de
datos. Requiere admin scope.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Cambia el active model. Requiere admin scope. Envía `null` o una cadena vacía en
`model_id` para restablecerlo.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Código | Estado | Descripción |
|--------|--------|-------------|
| `invalid_model_id` | 400 | model_id es demasiado largo o contiene caracteres de control |
| `unknown_model` | 400 | No hay etiquetas para el modelo indicado en la base de datos |

## POST /api/wd-tagger/batch

Ejecutar etiquetado por lotes en múltiples archivos. Si se especifica `file_ids`, solo se procesan esos archivos. Si se omite, selecciona automáticamente archivos sin etiquetar hasta `limit`.

### Límite de velocidad

HEAVY

### Solicitud

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Parámetro | Tipo | Requerido | Límite | Descripción |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | No | Máx 500 | Array de IDs de archivo objetivo. Si se omite, se seleccionan automáticamente archivos sin etiquetar |
| `limit` | int | No | - | Máx archivos a procesar cuando se omite `file_ids`. Por defecto `100` |
| `force` | boolean | No | - | Si es `true`, sobrescribir etiquetas existentes. Por defecto `false` |
| `scan_root` | string | No | - | Filtrar por ruta de raíz de escaneo. Cadena vacía para todos los archivos |

### Respuesta

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `batch_too_large` | 400 | `file_ids` excede 500 elementos |
| `batch_error` | 409 | Un trabajo por lotes ya está en ejecución |

## POST /api/wd-tagger/batch/cancel

Cancelar un trabajo de etiquetado por lotes en ejecución.

### Límite de velocidad

WRITE

### Solicitud

Sin cuerpo requerido.

### Respuesta

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `job_not_running` | 404 | Sin trabajo de etiquetado por lotes en ejecución |

## GET /api/wd-tagger/stats

Obtener estadísticas de etiquetado de WD Tagger.

### Parámetros

Ninguno

### Respuesta

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_tagged` | int | Número de archivos etiquetados |
| `total_tags` | int | Número total de etiquetas almacenadas |
| `models` | object | Número de archivos etiquetados por modelo |
| `untagged_unknown` | int | Número de archivos sin metadatos (`unknown`) y sin etiquetas de WD |

## GET /api/wd-tagger/untagged

Listar archivos sin metadatos (`unknown`) que aún no han sido etiquetados. Admite paginación.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `limit` | int | No | Número de resultados. 1-500, por defecto `100` |
| `offset` | int | No | Número de resultados a saltar. Por defecto `0` |

### Respuesta

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Leer metadatos XMP de un archivo específico.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de archivo (parámetro de ruta) |

### Respuesta

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `file_not_found` | 404 | El archivo no existe o ha sido eliminado lógicamente |

## GET /api/wd-tagger/vlm/test

Probar conectividad a un servidor VLM (Modelo de Lenguaje de Visión). Verifica la accesibilidad de un endpoint de API compatible con OpenAI.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `url` | string | Sí | URL del servidor VLM (parámetro de consulta) |

### Respuesta

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `missing_url` | 400 | Parámetro `url` no proporcionado |
| `invalid_url` | 400 | Formato de URL inválido |

## GET /api/wd-tagger/vlm/models

Listar modelos disponibles en un servidor VLM. Consulta el endpoint `/v1/models` compatible con OpenAI.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `url` | string | Sí | URL del servidor VLM (parámetro de consulta) |

### Respuesta

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `missing_url` | 400 | Parámetro `url` no proporcionado |
| `invalid_url` | 400 | Formato de URL inválido |
| `vlm_connection_error` | 502 | Fallo de conexión al servidor VLM |

## POST /api/wd-tagger/model/download

Descargar un modelo de WD Tagger. Obtiene archivos de modelo de Hugging Face y los guarda localmente.

### Límite de velocidad

HEAVY

### Solicitud

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `repo` | string | No | Nombre del repositorio de Hugging Face. Si se omite, utiliza el valor `model` de la configuración |

### Respuesta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Errores

| Código | Estado | Descripción |
|--------|--------|-------------|
| `unknown_model` | 400 | Repositorio de modelo desconocido. `hint` contiene lista de modelos conocidos |
| `download_failed` | 500 | Descarga falló |

## GET /api/wd-tagger/model/status

Verificar el estado de descarga de un modelo de WD Tagger.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `repo` | string | No | Nombre del repositorio de Hugging Face (parámetro de consulta). Si se omite, utiliza el valor `model` de la configuración |

### Respuesta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `repo` | string | Nombre del repositorio siendo verificado |
| `downloaded` | boolean | Si el modelo se ha descargado localmente |
| `path` | string/null | Ruta del modelo local si está descargado |
| `known_models` | object | Todos los modelos soportados (nombre del repositorio -> nombre mostrado) |

## User profile CRUD (v4.197.0+)

API para hacer CRUD de tagger profiles creados por el usuario desde la UI de la página Tools. Todos los endpoints requieren admin scope. El formato de error común es `{ok: false, error, code, ...extra}`. El body de la solicitud tiene un **hard cap de 1MB** (`code: profile_too_large`, 413). `id` debe cumplir el regex `^[a-z0-9][a-z0-9_-]{0,63}$`.

### POST /api/wd-tagger/profiles

Crear un nuevo profile de usuario.

**Solicitud**: profile JSON (schema v2, `profile_version: "2"`). El campo `builtin` se sobrescribe forzosamente a `false` del lado del servidor.

**Respuesta (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Campo | Descripción |
|---|---|
| `profile` | Profile guardado (se garantiza `builtin: false`) |
| `origin` | Siempre `"user"` |
| `overrides_builtin` | `true` si existe un profile builtin con el mismo id (ruta avanzada) |

**Errores**:

| status | code | condición |
|---|---|---|
| 400 | `validation_failed` | El JSON viola el schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | El `id` del body no coincide con el regex |
| 409 | `id_conflict` | Mismo id que un profile de usuario existente |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Obtener el profile completo schema v2 del id especificado (la UI lo llama al editar / duplicar / Export).

**path**: `id` (se requiere verificación por regex)

**Respuesta (200)**:
{Mismo formato que POST: profile / origin / overrides_builtin}

**Errores**:
- 400 `invalid_id` (el id del path no coincide con el regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Actualizar un profile de usuario existente.

**path**: `id` (se requiere verificación por regex)

**Solicitud**: profile JSON. `body.id` debe coincidir con el id del path (para renombrar, guiar la UI a `Duplicate → Delete`).

**Respuesta (200)**: Mismo formato que POST.

**Errores**:

| status | code | condición |
|---|---|---|
| 400 | `id_immutable` | El id del path y el id del body no coinciden |
| 400 | `invalid_id` | El id del path no coincide con el regex |
| 400 | `validation_failed` | Violación del schema |
| 403 | `builtin_read_only` | El id del path es un profile builtin (no hay archivo correspondiente del lado del usuario) |
| 404 | `not_found` | id no registrado |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Eliminar un profile de usuario.

**path**: `id`

**Respuesta (200)**:
```json
{"ok": true, "deleted": true}
```

**Errores**:

| status | code | condición |
|---|---|---|
| 400 | `invalid_id` | id del path inválido |
| 403 | `builtin_read_only` | Solo builtin, sin override del usuario |
| 404 | `not_found` | id no registrado |
| 409 | `in_use` | Este profile es el modelo activo (incluye `extra.active_model_id`). En la UI, cambia el profile activo vía `PUT /api/wd-tagger/active-model` y luego reintenta |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. Hace HEAD de cada `files[]` en HuggingFace y, para los que tienen `required: true`, realiza una descarga atómica por archivo (la caché reutiliza la ruta existente).

**path**: `id`

**body**: no requerido

**Comportamiento**:
- per-file timeout: 30s
- timeout total: 60s
- redirect: solo allowlist de subdominios `huggingface.co` / `hf.co`, máximo 5 hops; userinfo (`user:pass@`) es SSRFBlocked

**Respuesta (200, éxito)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

Valores de `status`:
- `downloaded`: descargado en esta ejecución
- `cached`: ya existe localmente (solo HEAD)
- `skipped_optional`: `required: false` y 404 / HEAD falló

**Errores (status / code)**:

| status | code | condición |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | id del path inválido / archivo required es 404 en HF |
| 404 | `not_found` | profile no registrado |
| 408 | `timeout` | excedió el total de 60s |
| 502 | `ssrf_blocked` | redirect fuera de la allowlist de HF / contiene userinfo / el scheme no es http(s) |
| 502 | `hf_unavailable` | HF devolvió 5xx |

En caso de error, el body tiene la forma `{"ok": false, "code": ..., "error": ..., "files": [...resultados parciales...], "detail": "..."}`.

### Formato de profile JSON (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // Ruta del repo de HF "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // siempre false para origen de usuario (el servidor lo fuerza)
}
```

Para más detalles, consulta `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), o la implementación de referencia builtin (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
