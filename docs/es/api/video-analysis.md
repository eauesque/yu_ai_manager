# API de Análisis de Vídeo

APIs para gestionar la configuración del análisis de vídeo y verificar estado. Controla la configuración para extraer fotogramas clave de archivos de vídeo.

## GET /api/video-analysis/config

Obtener la configuración actual del análisis de vídeo. Devuelve la configuración guardada combinada con valores predeterminados.

### Parámetros

Ninguno

### Respuesta

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| Campo | Tipo | Predeterminado | Descripción |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Si el análisis de vídeo está habilitado |
| `keyframe_count` | int | `4` | Número de fotogramas clave a extraer (1-16) |
| `strategy` | string | `"uniform"` | Estrategia de extracción de fotogramas clave. `uniform` (espaciados uniformemente), `scene` (detección de cambio de escena), `single` (solo fotograma único) |
| `scene_threshold` | float | `0.4` | Umbral de detección de cambio de escena (0.0-1.0). Se utiliza cuando `strategy` es `scene` |
| `store_per_keyframe` | boolean | `false` | Si cada fotograma clave se debe almacenar individualmente |

## POST /api/video-analysis/config

Guardar la configuración del análisis de vídeo. Solo se actualizan los campos especificados; los campos omitidos conservan sus valores existentes.

### Limitación de Velocidad

WRITE

### Solicitud

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

Todos los campos son opcionales. Solo se actualizan los campos especificados.

| Parámetro | Tipo | Requerido | Restricciones | Descripción |
|-----------|------|----------|-------------|-------------|
| `enabled` | boolean | No | - | Si el análisis de vídeo está habilitado |
| `keyframe_count` | int | No | 1-16 | Número de fotogramas clave a extraer |
| `strategy` | string | No | `uniform`, `scene`, o `single` | Estrategia de extracción de fotogramas clave |
| `scene_threshold` | float | No | 0.0-1.0 | Umbral de detección de cambio de escena |
| `store_per_keyframe` | boolean | No | - | Si cada fotograma clave se debe almacenar individualmente |

### Respuesta

Devuelve la configuración combinada después de guardar (mismo formato que GET).

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Errores

| Estado | Código | Condición |
|--------|------|-----------|
| 400 | `invalid_json` | El cuerpo de la solicitud no es un objeto JSON |
| 400 | `invalid_value` | Error de validación (tipo incorrecto, valor fuera de rango, estrategia inválida, etc.) |

## GET /api/video-analysis/status

Obtener información de estado del análisis de vídeo. Devuelve disponibilidad de ffmpeg, recuento de archivos de vídeo y número de archivos con fotogramas clave extraídos.

### Parámetros

Ninguno

### Respuesta

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ffmpeg` | boolean | Si ffmpeg está disponible en el sistema |
| `video_files` | int | Número total de archivos de vídeo en la base de datos (excluyendo eliminados lógicamente). Extensiones soportadas: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Número de archivos que tienen fotogramas clave extraídos |
