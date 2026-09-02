# Protocolo QR de YU v1 — Especificación de Payload Unificada

**Versión:** 1.0
**Fecha:** 2026-02-23
**Aplicación objetivo:** YU AI Manager (TagDB)

---

## Descripción General

YU AI Manager soporta compartir prompts y diagnósticos de errores vía códigos QR.
Este documento proporciona una especificación unificada para el formato de payload de QR.

### Librerías Utilizadas

| Propósito | Librería | Versión |
|------|-----------|-----------|
| Generación de QR | QRCode.js | 1.0.0 |
| Lectura de QR | jsQR | 1.4.0 |

### Límites de Capacidad de QR

- Máximo caracteres: **2,953** (nivel de corrección de errores M)
- Por encima de 2,500 caracteres: el JSON meta se minimiza e intenta nuevamente
- Por encima de 2,953 caracteres: error (`qr.info.too_long`)

---

## Tipo de Payload 1 — Compartir Prompt

### Origen

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### Esquema JSON

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<prompt positivo>",
  "n":   "<prompt negativo>",
  "src": "TagDB",
  "m":   "<nombre de modelo>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<escala CFG>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Definiciones de Campo

| Clave | Tipo | Requerido | Descripción | Límite |
|------|-----|------|------|------|
| `v` | string | ✅ | Versión del protocolo. Actualmente `"1.0"` | — |
| `t` | string | ✅ | Tipo de payload. Actualmente siempre `"prompt"` | — |
| `p` | string | ✅ | Prompt positivo | 2,000 caracteres |
| `n` | string | ✅ | Prompt negativo | 1,000 caracteres |
| `src` | string | ✅ | Identificador del emisor. Actualmente siempre `"TagDB"` | — |
| `m` | string | — | Nombre del modelo | — |
| `s` | string | — | Valor de seed | — |
| `st` | string | — | Recuento de pasos | — |
| `cfg` | string | — | Escala CFG | — |
| `sa` | string | — | Nombre de sampler | — |
| `sz` | string | — | Tamaño de imagen en formato `"WxH"` | — |

---

## Modos de QR — 4 Tipos

### Modo `positive`

```
qrText = shareData.p
```

- Contenido: Solo texto del prompt positivo
- Caso de uso: Compartir directamente prompts de texto

### Modo `negative`

```
qrText = shareData.n
```

- Contenido: Solo texto del prompt negativo

### Modo `meta`

```
qrText = JSON.stringify(shareData, null, 0)
```

- Contenido: El payload JSON de Compartir Prompt completo, compactado
- Se retrocede a `JSON.stringify` formateado cuando el resultado excede 2,500 caracteres

### Modo `url`

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Contenido: Una URL a la página de compartir de YU AI Manager
- Deshabilitado en localhost (`localhost` / `127.0.0.1`)

---

## Tipo de Payload 2 — Diagnóstico de Error

### Origen

- Generado en errores HTTP -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### Esquema JSON

```json
{
  "s": "<código de estado HTTP>",
  "p": "<ruta de solicitud>",
  "v": "<APP_VERSION>"
}
```

### Definiciones de Campo

| Clave | Tipo | Descripción | Límite |
|------|-----|------|------|
| `s` | string | Código de estado HTTP (`"404"`, `"500"`, etc.) | — |
| `p` | string | Ruta de solicitud | 80 caracteres |
| `v` | string | Versión de la aplicación (del archivo `APP_VERSION`) | — |

---

## Procedimiento de Decodificación de URL de Compartir

Decodificación en la página de compartir (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## Parámetros de Generación de QR

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 en páginas de error
  height:       200,   // 180 en páginas de error
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // Corrección de errores del 15%
});
```

---

## Extensiones Futuras (v1.x)

| Característica | Estado | Notas |
|------|------|------|
| Exportación de QR de colección (múltiples imágenes) | No implementado | Planeado como tipo de payload 3 |
| Tipo `t: "collection"` | No definido | Lista de ID de archivo + nombre de colección |
| Compresión (gzip + Base64) | No implementado | Alternativa para prompts que excedan 2,953 caracteres |

---

## Archivos de Implementación

| Archivo | Rol |
|----------|------|
| `routes/share.py` | Blueprint de API de Compartir |
| `routes/share_ops/payload_build.py` | Generación de payload |
| `routes/share_ops/prompt_extract.py` | Extracción de datos de prompt |
| `core/web/app_factory_handlers.py` | Generación de datos QR de error |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | Construcción y renderizado de QR |
| `static/js/runtime/tools/runtime-tools-qr.js` | Manejadores de UI de QR |
| `static/js/share/share-qr.js` | Decodificación de imagen QR |
| `static/js/share/share-page.js` | Visualización de página de compartir |
| `static/vendor/qrcode.min.js` | Librería QRCode.js |
| `static/vendor/jsQR.min.js` | Librería jsQR |
