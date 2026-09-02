# API de Depuración

APIs internas para depuración y diagnóstico. Se utiliza para inspeccionar metadatos de archivos, verificar información de modelos y gestionar directorios raíz escaneados.

Estos endpoints no tienen UI frontend y están destinados principalmente para desarrollo y solución de problemas.

## GET /api/debug/file-meta/<file_id>

Inspeccionar metadatos detallados de un archivo. Devuelve metadatos almacenados en la BD, y para archivos dentro de archivos ZIP, también devuelve resultados extraídos recientemente.

### Autenticación

Sesión PIN o API Key

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `file_id` | int | ID de archivo (parámetro de ruta) |

### Respuesta

```json
{
  "id": 123,
  "path": "/images/sample.png",
  "meta_source": "a1111_png",
  "parser_version": 5,
  "format": "a1111",
  "model_name": "sd_xl_base_1.0",
  "raw_prompt_length": 256,
  "raw_prompt_preview": "masterpiece, best quality, ...",
  "raw_negative_preview": "lowres, bad anatomy, ...",
  "raw_meta_json_length": 1024,
  "raw_meta_json_preview": "{\"steps\": 20, ...}",
  "has_v4_prompt": false,
  "has_comment": true
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | int | ID de archivo |
| `path` | string | Ruta del archivo |
| `meta_source` | string | Fuente de metadatos (`a1111_png`, `novelai_v4_png`, etc.) |
| `parser_version` | int | Versión del analizador |
| `format` | string | Formato de plantilla |
| `model_name` | string/null | Nombre del modelo |
| `raw_prompt_length` | int | Recuento de caracteres del prompt bruto |
| `raw_prompt_preview` | string | Primeros 300 caracteres del prompt bruto |
| `raw_negative_preview` | string | Primeros 300 caracteres del prompt negativo |
| `raw_meta_json_length` | int | Recuento de caracteres del JSON de metadatos bruto |
| `raw_meta_json_preview` | string | Primeros 500 caracteres del JSON de metadatos bruto |
| `has_v4_prompt` | bool | Si contiene un prompt V4 de NovelAI |
| `has_comment` | bool | Si contiene un campo Comment |

Para archivos dentro de archivos ZIP, se añade un campo `fresh_extract` con resultados de reextracción:

```json
{
  "fresh_extract": {
    "meta_source": "a1111_png",
    "format": "a1111",
    "raw_meta_json_length": 1024,
    "raw_meta_json_preview": "{...}",
    "has_v4_prompt": false,
    "success": true,
    "raw_prompt_preview": "masterpiece, ..."
  }
}
```

### Errores

| Estado | Descripción |
|--------|-------------|
| 404 | Archivo no encontrado |

## GET /api/debug/model-check

Verificar el estado de almacenamiento de `model_name` en la tabla de plantillas. Devuelve estadísticas y muestras para registros con y sin nombres de modelo.

### Autenticación

Sesión PIN o API Key

### Parámetros

Ninguno

### Respuesta

```json
{
  "total_templates": 1000,
  "with_model_name": 850,
  "without_model_name": 150,
  "samples_with_model": [
    {
      "file_id": 1,
      "model_name": "sd_xl_base_1.0",
      "model_hash": "abc123",
      "format": "a1111"
    }
  ],
  "samples_without_model": [
    {
      "file_id": 42,
      "model_name": null,
      "format": "comfy",
      "raw_meta_json_preview": "{...}"
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `total_templates` | int | Número total de plantillas |
| `with_model_name` | int | Número de registros con nombre de modelo configurado |
| `without_model_name` | int | Número de registros sin nombre de modelo |
| `samples_with_model` | array | Muestras con nombre de modelo (hasta 10) |
| `samples_without_model` | array | Muestras sin nombre de modelo (hasta 5) |

## GET /api/scanned-roots

Extraer directorios raíz de archivos registrados en la BD y devolverlos con recuentos de archivos. Agrega tanto raíces configuradas como raíces de archivos que no pertenecen a ninguna raíz configurada.

### Autenticación

Sesión PIN o API Key

### Parámetros

Ninguno

### Respuesta

```json
{
  "roots": [
    {
      "path": "C:\\Images\\AI",
      "count": 5000
    },
    {
      "path": "D:\\Archives",
      "count": 1200
    }
  ]
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `roots` | array | Array de directorios raíz (ordenado por recuento de archivos descendente, máx 50) |
| `roots[].path` | string | Ruta del directorio |
| `roots[].count` | int | Número de archivos bajo esta ruta |

### Errores

| Estado | Descripción |
|--------|-------------|
| 500 | Fallo al calcular resumen de raíces |

## POST /api/debug/query

Ejecutar una consulta SQL de solo lectura. Requiere la variable de entorno `YU_DEBUG_MODE=1` y solo permite acceso desde localhost.

### Límite de velocidad

WRITE

### Autenticación

Sesión PIN o API Key (solo localhost + `YU_DEBUG_MODE=1`)

### Solicitud

```json
{
  "sql": "SELECT id, path, meta_source FROM files LIMIT 10",
  "limit": 100
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `sql` | string | Sí | Sentencia SELECT a ejecutar |
| `limit` | int | No | Número máximo de filas a devolver (por defecto: 100, máx: 10000) |

### Restricciones

- Solo se permiten sentencias SELECT (INSERT, UPDATE, DELETE, etc. se rechazan)
- No se permiten múltiples sentencias (separadas por punto y coma)
- Las consultas que contienen palabras clave de escritura (DROP, ALTER, CREATE, etc.) se rechazan

### Respuesta

```json
{
  "columns": ["id", "path", "meta_source"],
  "rows": [
    {"id": 1, "path": "/images/test.png", "meta_source": "a1111_png"}
  ],
  "row_count": 1,
  "truncated": false
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `columns` | string[] | Array de nombres de columnas |
| `rows` | object[] | Filas de resultado (cada fila es un objeto con claves de nombres de columnas) |
| `row_count` | int | Número de filas devueltas |
| `truncated` | bool | `true` si los resultados fueron truncados por el límite |

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | SQL vacío, múltiples sentencias, consulta no-SELECT, contiene operaciones de escritura, error de sintaxis SQL |
| 403 | Modo debug no habilitado, o acceso desde no-localhost |

## POST /api/scanned-roots/purge

Eliminar permanentemente todos los registros de archivo bajo la ruta especificada de la BD. Los registros relacionados (etiquetas, plantillas, etc.) se eliminan en cascada. Las etiquetas no utilizadas se eliminan automáticamente.

### Límite de velocidad

DESTRUCTIVE

### Autenticación

Sesión PIN o API Key

### Solicitud

```json
{
  "path": "C:\\Images\\OldFolder"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `path` | string | Sí | Ruta raíz a purgar. Todos los archivos bajo esta ruta serán eliminados |

### Respuesta

```json
{
  "purged": 150,
  "path": "C:\\Images\\OldFolder"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `purged` | int | Número de registros de archivo eliminados |
| `path` | string | La ruta especificada |

### Errores

| Estado | Descripción |
|--------|-------------|
| 400 | Ruta no especificada |
| 500 | Operación de purga falló |
