# API de Archivos

APIs para recuperar detalles de archivo, miniaturas y medios originales.

## GET /api/file/<id>

Recuperar metadatos detallados para un archivo.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de archivo (parámetro de ruta) |

### Respuesta

```json
{
  "id": 42,
  "path": "/images/output/00042.png",
  "filename": "00042.png",
  "size": 1234567,
  "mtime": 1709500000,
  "width": 1024,
  "height": 1536,
  "meta_type": "a1111_png",
  "model_name": "animagine-xl-3.1",
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Imagen de miniatura (WebP). Soporta almacenamiento en caché ETag.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de archivo |
| `size` | int | Tamaño de miniatura (predeterminado 300) |

### Respuesta

- Content-Type: `image/webp`
- Soporte ETag / If-None-Match (304 Not Modified)
- Caché: 24 horas

## GET /api/original/<id>

Transmitir el archivo original. También soporta archivos dentro de archivos ZIP.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | int | ID de archivo |

### Respuesta

- Content-Type: MIME type del archivo
- Content-Disposition: `inline`
- Soporte de solicitud Range (para búsqueda de video)

## POST /api/convert

Conversión de formato de prompt (A1111 <-> NAI).

### Solicitud

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Respuesta

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Lista de IDs de miniatura para un contenedor (carpeta/ZIP), excluyendo entradas ya almacenadas en caché.

### Parámetros

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `keys` | string | Claves de contenedor (separadas por comas) |
