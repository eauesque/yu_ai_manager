# API de OCR

API para extracción de texto (OCR) de imágenes, vídeos y PDFs, junto con traducción, generación de imagen superpuesta, exportación, evaluación comparativa y gestión de motores.

## POST /api/ocr/<file_id>

Ejecutar OCR en un archivo individual y guardar el resultado en la base de datos.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Tipo de tarea de OCR. Uno de `ocr` / `ocr_document` / `ocr_manga`. Por defecto: `ocr` |
| `language` | string | No | Pista de idioma. Por defecto: `auto` |
| `server_id` | string | No | ID del servidor de análisis a usar. Auto-seleccionado si se omite |

### Respuesta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### Errores

- `400` — Valor de tarea inválido
- `404` — Archivo no encontrado
- `500` — Fallo al resolver motor OCR / Error de ejecución OCR

---

## GET /api/ocr/result/<file_id>

Recuperar un resultado guardado de OCR.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Filtrar por tipo de tarea |
| `engine` | string | No | Filtrar por nombre de motor |
| `all` | string | No | Si se establece a cualquier valor, devuelve todos los resultados |

### Respuesta (resultado encontrado)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### Respuesta (con `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Respuesta (sin resultado)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

Eliminar resultados de OCR guardados.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "",
  "engine": ""
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Filtrar por tipo de tarea. Cadena vacía se refiere a todas las tareas |
| `engine` | string | No | Filtrar por nombre de motor. Cadena vacía se refiere a todos los motores |

### Respuesta

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

Ejecutar OCR en múltiples archivos en lote.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parámetro | Tipo | Requerido | Límite | Descripción |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | Sí | Máx 500 | Array de IDs de archivo de destino |
| `task` | string | No | — | Tipo de tarea de OCR. `ocr` / `ocr_document` / `ocr_manga`. Por defecto: `ocr` |
| `language` | string | No | — | Pista de idioma. Por defecto: `auto` |
| `server_id` | string | No | — | ID del servidor de análisis a usar |

### Respuesta (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### Errores

- `400` — `file_ids` está vacío / excede 500 / valor de tarea inválido
- `500` — Fallo al resolver motor OCR

---

## POST /api/ocr/video/<file_id>

Extraer fotogramas clave de un archivo de vídeo y ejecutar OCR en cada fotograma.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Tipo de tarea de OCR. Por defecto: `ocr` |
| `language` | string | No | Pista de idioma. Por defecto: `auto` |
| `server_id` | string | No | ID del servidor de análisis a usar |
| `keyframe_count` | int | No | Número de fotogramas clave a extraer. Rango: 1-16. Por defecto: `4` |
| `strategy` | string | No | Estrategia de extracción de fotogramas clave. Por defecto: `uniform` |

### Respuesta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### Errores

- `400` — El archivo no es un vídeo
- `404` — Archivo no encontrado
- `500` — Fallo al resolver motor OCR / Error de ejecución de OCR de vídeo

---

## POST /api/ocr/pdf/<file_id>

Convertir páginas PDF a imágenes y ejecutar OCR. Útil para PDFs escaneados sin capa de texto.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Tipo de tarea de OCR. Por defecto: `ocr_document` |
| `language` | string | No | Pista de idioma. Por defecto: `auto` |
| `server_id` | string | No | ID del servidor de análisis a usar |
| `page_range` | string | No | Rango de páginas (ej. `"1-5"`, `"1,3,5"`). Cadena vacía significa todas las páginas |
| `dpi` | int | No | Resolución de renderización. Rango: 72-400. Por defecto: `200` |

### Respuesta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### Errores

- `400` — El archivo no es un PDF
- `404` — Archivo no encontrado
- `500` — Fallo al resolver motor OCR / Error de ejecución de OCR de PDF

---

## POST /api/ocr/bbox/<file_id>

Detectar cuadros delimitadores de texto para resultados de OCR existentes. Utilizado como un segundo paso para agregar información de posición a regiones de texto previamente extraídas.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "",
  "server_id": ""
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `task` | string | No | Tipo de tarea de OCR objetivo |
| `server_id` | string | No | ID del servidor de análisis a usar |

### Respuesta (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### Errores

- `400` — No se encontraron regiones de texto / Motor VLM requerido
- `404` — Resultado de OCR no encontrado (ejecutar OCR primero) / Archivo no encontrado
- `500` — Fallo al resolver motor OCR / Error de detección de bbox

---

## GET /api/ocr/engines

Listar motores de OCR disponibles (servidores de análisis) con puntuaciones por tarea.

### Parámetros

Ninguno

### Respuesta

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

Obtener estado del dispositivo NPU (Unidad de Procesamiento Neural) y configuración de optimización recomendada.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `task` | string | No | Tipo de tarea para recomendaciones de optimización. Por defecto: `ocr` |

### Respuesta

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

Traducir un resultado de OCR existente al idioma especificado. La traducción se guarda en la base de datos.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `target_lang` | string | Sí | Código de idioma de destino (ej. `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | No | ID del servidor de análisis a usar |
| `task` | string | No | Tipo de tarea de OCR objetivo |

### Respuesta (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### Errores

- `400` — `target_lang` no especificado
- `404` — Resultado de OCR no encontrado
- `500` — Error de ejecución de traducción

---

## GET /api/ocr/translations/<file_id>

Obtener la lista de resultados de traducción para un archivo.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `target_lang` | string | No | Filtrar por código de idioma |

### Respuesta

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

Generar una imagen superpuesta con resultados de OCR (o traducciones) renderizados encima de la imagen original.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `mode` | string | No | Modo de visualización. `translated` / `original` / `both`. Por defecto: `translated` |
| `target_lang` | string | No | Filtrar por idioma de traducción |
| `format` | string | No | Formato de imagen de salida. `png` / `jpeg`. Por defecto: `png` |
| `task` | string | No | Tipo de tarea de OCR objetivo |

### Respuesta

- Content-Type: `image/png` o `image/jpeg`
- Nombre de archivo: `ocr_overlay_{file_id}.{ext}`

### Errores

- `400` — Valor de modo / formato inválido
- `404` — Resultado de OCR no encontrado / Archivo no encontrado
- `500` — Error de generación de imagen superpuesta

---

## GET /api/ocr/export/<file_id>

Exportar un resultado de OCR en el formato especificado como descarga de archivo.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | Sí | ID de archivo (parámetro de ruta) |
| `format` | string | No | Formato de exportación. `txt` / `md` / `json` / `pdf`. Por defecto: `md` |
| `task` | string | No | Tipo de tarea de OCR objetivo |
| `include_translation` | string | No | Si se establece a cualquier valor, incluye traducciones |
| `target_lang` | string | No | Código de idioma de la traducción a incluir |

### Respuesta

- Content-Type: Tipo MIME apropiado para el formato
- Content-Disposition: `attachment; filename=...`

### Errores

- `400` — Valor de formato inválido
- `404` — Resultado de OCR no encontrado

---

## POST /api/ocr/export/batch

Exportación masiva de resultados de OCR para múltiples archivos. Admite descarga ZIP o guardar en servidor.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_ids` | int[] | Sí | Array de IDs de archivo de destino |
| `format` | string | No | Formato de exportación. `txt` / `md` / `json` / `pdf` / `overlay`. Valores por defecto de la configuración de extensión |
| `output_dir` | string | No | Ruta absoluta para guardar en servidor. Si se omite, devuelve descarga ZIP |
| `overlay_mode` | string | No | Modo de superposición (cuando `format=overlay`). `translated` / `original` / `both`. Por defecto: `translated` |
| `target_lang` | string | No | Código de idioma de traducción |
| `include_translation` | bool | No | Si incluir traducciones. Por defecto: `false` |

### Respuesta (descarga ZIP)

- Content-Type: `application/zip`
- Nombre de archivo: `ocr_export_batch.zip` (formatos de texto) o `ocr_overlay_batch.zip` (formato de superposición)

### Respuesta (guardar en servidor)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### Errores

- `400` — `file_ids` está vacío / valor de formato inválido / `output_dir` no es una ruta absoluta
- `403` — `output_dir` es un directorio prohibido
- `404` — No se encontraron resultados de OCR

---

## POST /api/ocr/benchmark

Ejecutar una evaluación comparativa de OCR para medir precisión y rendimiento. Requiere casos de evaluación comparativa (pares de imagen + texto de verdad fundamental).

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `task` | string | No | Tipo de tarea para evaluar. Por defecto: `ocr` |
| `server_id` | string | No | ID del servidor de análisis a usar |
| `benchmark_dir` | string | No | Ruta de directorio para casos de evaluación comparativa. Por defecto: `extensions/builtin_ocr/benchmarks/` |

### Respuesta (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### Errores

- `404` — No se encontraron casos de evaluación comparativa
- `500` — Fallo al resolver motor OCR / Error de ejecución de evaluación comparativa

---

## GET /api/ocr/benchmark/cases

Listar casos de evaluación comparativa disponibles.

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `dir` | string | No | Ruta de directorio para casos de evaluación comparativa |

### Respuesta

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

Listar perfiles del modelo OCR con configuraciones de puntuación por tarea.

### Parámetros

Ninguno

### Respuesta

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

Obtener y fusionar perfiles de modelo publicados en la comunidad desde una URL.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `url` | string | Sí | URL del JSON de perfil |

### Respuesta (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Errores

- `400` — `url` no especificado
- `500` — Obtención o fusión falló

---

## PUT /api/ocr/profiles/<model_prefix>

Actualizar manualmente puntuaciones para un perfil de modelo.

### Límite de velocidad

WRITE

### Solicitud

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `model_prefix` | string | Sí | Prefijo de nombre de modelo (parámetro de ruta) |
| `scores` | object | Sí | Objeto con tipos de tarea como claves y puntuaciones (enteros) como valores |

### Respuesta

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### Errores

- `400` — `scores` no especificado
