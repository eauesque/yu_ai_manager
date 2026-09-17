# API de Rasterización de SVG

API para convertir imágenes vectoriales SVG a mapas de bits PNG/WebP.
Diseñado para integración de canalización img2img: los datos de imagen base64 devueltos se pueden pasar directamente a NovelAI Bridge o SD WebUI Bridge.

## GET /api/svg/info

Verificar disponibilidad de rasterización SVG.

- **Limitación de velocidad**: Ninguna (GET)

### Respuesta

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `available` | bool | Si la rasterización está disponible |
| `backend` | string \| null | Backend activo (`"resvg"` o `null`) |

---

## POST /api/svg/rasterize

Rasterizar un SVG a un mapa de bits PNG/WebP.

- **Limitación de velocidad**: HEAVY

### Cuerpo de Solicitud

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|-------------|
| `file_id` | int | *1 | ID de archivo SVG de la base de datos |
| `svg_path` | string | *1 | Ruta absoluta a un archivo SVG |
| `svg_data` | string | *1 | Cadena XML SVG en línea |
| `width` | int | No | Ancho de salida (predeterminado: 1024) |
| `height` | int | No | Alto de salida (predeterminado: 1024) |
| `format` | string | No | `"png"` o `"webp"` (predeterminado: `"png"`) |
| `background` | string | No | Color de fondo (p. ej. `"#ffffff"`). Transparente si se omite |

> *1: Proporcione exactamente uno de `file_id`, `svg_path` o `svg_data`.

### Ejemplo de Solicitud

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Respuesta

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ok` | bool | Bandera de éxito |
| `base64` | string | Datos PNG/WebP codificados en base64 |
| `width` | int | Ancho de salida real |
| `height` | int | Alto de salida real |
| `format` | string | Formato de salida |
| `size_bytes` | int | Tamaño binario en bytes |

### Respuesta de Error

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## Integración MCP

Use Claude Desktop para construir una canalización SVG → img2img:

```
# Paso 1: Rasterizar el SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Paso 2: Pasar el base64 devuelto a img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### Herramientas MCP

| Herramienta | Descripción |
|------|-------------|
| `svg_info` | Verificar disponibilidad de rasterización |
| `svg_rasterize` | Rasterizar SVG a PNG/WebP |

---

## Dependencias

| Paquete | Licencia | Propósito |
|---------|---------|---------|
| `resvg` | MIT | Renderizador SVG basado en Rust (multiplataforma) |

Si `resvg` no está instalado, las miniaturas muestran un marcador de posición y la API devuelve HTTP 501.

```bash
pip install resvg
```
