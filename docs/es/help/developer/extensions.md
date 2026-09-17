# Extensiones

YU AI Manager puede ampliar sus funciones con el sistema de extensiones.
Actualmente viene con 43 extensiones integradas, clasificadas en 6 categorías.

## Lista de extensiones integradas

### Extracción de metadatos (metadata)

| Extensión | Descripción |
|-----------|------|
| builtin-a1111 | Extracción de metadatos PNG/WebP/WebM de Automatic1111 / SD WebUI |
| builtin-novelai-v3 | Extracción de metadatos NovelAI V3 y anteriores |
| builtin-novelai-v4 | Extracción de metadatos NovelAI V4 (compatible con Character Prompts, Vibe Transfer) |
| builtin-comfyui | Análisis de JSON del flujo de trabajo ComfyUI |
| builtin-annotations | Guardado, búsqueda y operaciones en lote de anotaciones de archivos |
| builtin-ratings | Sistema de puntuación por estrellas (1〜5 estrellas) |
| builtin-tag-dictionary | Búsqueda, importación y división del diccionario de etiquetas Danbooru |

### Integración Bridge (bridge)

| Extensión | Descripción |
|-----------|------|
| builtin-sd-webui-bridge | Integración con SD WebUI / Forge (generación de imágenes, gestión de modelos) |
| builtin-nai-bridge | Integración con la API de NovelAI (generación de imágenes) |
| builtin-comfyui-bridge | Integración con ComfyUI (ejecución de flujos de trabajo) |

### Prompts (prompt)

| Extensión | Descripción |
|-----------|------|
| builtin-prompt-library | Biblioteca y organización de prompts |
| builtin-prompt-syntax | Resaltado de sintaxis de prompts y detección de errores (compatible con NAI/SD/DP) |
| builtin-prompt-simulator | Simulador de Dynamic Prompts, cálculo de pesos, conversión |
| builtin-sd-nai-convert | Conversión mutua de prompts SD ↔ NovelAI |

### IA (ai)

| Extensión | Descripción |
|-----------|------|
| builtin-analysis | Análisis de imágenes con IA (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | Etiquetado automático WD-Tagger (motores ONNX + VLM) |
| builtin-ocr | VLM OCR — extracción de texto, análisis estructurado, traducción |
| builtin-clip-search | Motor de búsqueda semántica de imágenes CLIP |
| builtin-clip-onnx | Backend del codificador CLIP ONNX Runtime |
| builtin-clip-coreml | Codificador CLIP Core ML (Apple Neural Engine) |
| builtin-hailo-semantic-search | Búsqueda semántica Hailo-10H |
| builtin-hailo-yolo-detect | Detección de objetos YOLO con Hailo-10H |
| builtin-hailo-genai | GenAI Hailo-10H (LLM/VLM/S2T) |
| builtin-speech-to-text | Transcripción de voz (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Análisis de audio (Whisper local / API de OpenAI) |
| builtin-video-analysis | Análisis de video con IA (múltiples fotogramas clave + Gemini) |
| builtin-inference | Detección del proveedor ONNX Runtime, aceleración GPU |

### Biblioteca (library)

| Extensión | Descripción |
|-----------|------|
| builtin-favorites-manager | Gestión de favoritos y colecciones |
| builtin-freeze-pullback | Generación de video Freeze & Pull-back (efecto Ken Burns) |
| builtin-download | Descarga en lote de imágenes seleccionadas en ZIP |
| builtin-chatlog | Importador y visor de registros de chat (Claude / ChatGPT) |
| builtin-md-viewer | Visor de archivos Markdown (búsqueda de texto completo FTS5) |
| builtin-cross-search | Búsqueda cruzada (MD, registros de chat, prompts, texto) |
| builtin-lan-share | Compartición de colecciones en LAN (autenticación por token con límite de tiempo) |
| builtin-stats | Información estadística (cronología, hitos) |
| builtin-trophy | Sistema de trofeos y logros |
| builtin-export | Hook de exportación (transformación de registros al exportar CSV) |

### Sistema (system)

| Extensión | Descripción |
|-----------|------|
| builtin-auto-scan-watcher | Detección automática de cambios de archivos, actualizaciones diferenciales |
| builtin-mcp-client | Gestión de conexiones a servidores MCP externos |
| builtin-backup | Copia de seguridad, restauración y programación de BD |
| builtin-sns-share | Compartición en redes sociales (Bluesky, X/Twitter) |
| builtin-webhook | Distribuidor de webhooks (entrega HTTP impulsada por eventos) |
| builtin-debug-check | CLI de diagnóstico de depuración |
| builtin-github-integration | Monitoreo de issues de GitHub, clasificación, seguimiento de PR/Discussion/Release |

## Gestión de extensiones

En la pestaña Extensions de Settings se pueden realizar las siguientes operaciones:

- **Habilitar/deshabilitar**: Cambio instantáneo con interruptor de palanca
- **Nueva instalación**: Instalar especificando la URL del repositorio Git
- **Marketplace**: Búsqueda de extensiones públicas e instalación con un clic
- **Actualización**: Actualizar extensiones basadas en Git a la última versión
- **Desinstalación**: Eliminar extensiones de terceros

### Gestión vía API

```bash
# Lista de extensiones
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Habilitar/deshabilitar
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Instalar desde Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Sandbox de extensiones

Las extensiones de terceros están protegidas por el sandbox.

### Niveles de confianza

| Nivel | Objetivo | Restricciones |
|--------|------|------|
| L0 (TRUSTED) | `builtin-*` | Sin restricciones |
| L2 (UNTRUSTED) | Otros | Restricciones de BD/FS/red |

### 4 fases del sandbox

1. **Capability Token**: Gestión de permisos con token firmado HMAC-SHA256. Validez de 24 horas
2. **SandboxedDB / SandboxedFS**: Las extensiones con solo `db:read` solo permiten SELECT. El acceso a archivos se controla por ruta
3. **SandboxedHTTPClient / ImportGuard**: Prevención SSRF, monitoreo de importación en tiempo de ejecución, detección de alteraciones SHA-256
4. **Aislamiento de proceso (Linux)**: Ejecutar extensiones L2 en proceso separado. IPC JSON-RPC 2.0 con socket Unix

### Aislamiento a nivel de SO (opcional)

- **Linux**: Generación automática de perfiles AppArmor
- **macOS**: sandbox-exec (experimental)
- **Windows**: Token restringido + Job Object

> **Consejo**: Para más detalles sobre el desarrollo de extensiones, consultar la sección "Desarrollo de extensiones".

## Estructura de directorios

```
extensions/builtin_<name>/
  extension.json            # Manifiesto (nombre, versión, permisos, etc.)
  <name>_ext.py             # Punto de entrada (expone get_blueprint())
  templates/<name>/          # Plantillas Jinja2
  core_impl/                 # Lógica de negocio (opcional)
```

### Campos obligatorios de extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Las categorías son 6 tipos: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## API de módulo de extensión v2 (compatible con ES Module)

Desde v4.29.0, las extensiones pueden escribirse con el patrón ES Module usando `<script type="module">` e Import Maps.

### Cómo habilitar

Agregar `"script_type": "module"` a `extension.json`:

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### Uso

Cambiar el `<script>` de la plantilla a `<script type="module">` e importar desde `yu-api`:

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Notificación toast
showToast('Guardado');

// Suscribirse a evento SSE
sseSubscribe('scan.progress', (data) => {
  console.log('Progreso:', data);
});

// Traducción i18n
const label = tr('my_ext.title', 'My Extension');

// Llamada a API (con encabezado CSRF automático)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Lista de API pública

| Función | Descripción |
|---|---|
| `showToast(message, isError?)` | Mostrar notificación toast |
| `sseSubscribe(eventType, handler)` | Suscribirse a evento SSE |
| `sseUnsubscribe(eventType, handler)` | Cancelar suscripción a evento SSE |
| `tr(path, a?, b?)` | Resolver clave de traducción i18n |
| `apiFetch(path, opts?)` | Wrapper fetch con CSRF |
| `apiUrl(path)` | Construir URL de API |
| `escapeHtml(text)` | Escapar caracteres especiales HTML |

### Definiciones de tipo TypeScript

Copiar `src/ts/extension-api/extension-api.d.ts` al proyecto de la extensión para habilitar el autocompletado y la verificación de tipos en el IDE.

### Compatibilidad con legado

Las extensiones con `"script_type": "classic"` (valor predeterminado) pueden seguir usando las funciones globales como `window.showToast()`. No es necesario reescribir las extensiones existentes.

## Documentación de desarrollo

Para los detalles de decisiones de diseño, precauciones conocidas y consejos de depuración sobre el desarrollo de extensiones y el sistema interno, visita [MD Viewer](/ext/md-viewer/). `docs/development/development_docs/` está registrado y también es compatible con la búsqueda de texto completo FTS5.
