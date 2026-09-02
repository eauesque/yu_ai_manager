# Centro de Documentación

Utilice este archivo como su "punto de entrada de documentación (centro oficial)".

**Última actualización**: 2026-05-13

## Importante

- README del Proyecto: [`../../README.es.md`](../../README.es.md)
- Registro de Cambios: [`../../CHANGELOG.es.md`](../../CHANGELOG.es.md)
- TODO Principal (fuente única de verdad): [`../../TODO.md`](../../TODO.md)

## Guías de Desarrollo

Las guías de desarrollo se encuentran como archivos individuales en `development/development_docs/`.

- **[TODO Rules](TODO_RULES.md)** — Reglas para escribir TODO (P0/P1/P2/P3 + categoría requerida)

### Documentos Principales (`development/development_docs/`)

| Documento | Contenido |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Comenzar consideración a 300 líneas, división obligatoria a 500 líneas |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Directorio de unidad de funciones, 100-250 líneas ideales |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Modelo de defensa en tres capas (validación estática/análisis/tiempo de ejecución) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | Uniforme `api_error()`, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Lista de puntos de entrada de todos los módulos |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Estrategias de prevención para 6 puntos de accidente |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Diseño de botones Tier A/B/C |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Patrón híbrido Explorer/Library |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Reglas de ubicación de documentos |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | Pruebas de fuzzing y burn-in de API + UI |

### Otros Documentos de Desarrollo

| Documento | Contenido |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Principios de diseño para desarrollo impulsado por IA |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Convención de operaciones por lotes |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Ciclo de vida de ganchos de extensión |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Lista de widgets de UI reutilizables |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | Especificación de sintaxis de prompt SD/NAI |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Codificación de nombres de archivos de archivo |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Tabla de compatibilidad de formatos de imagen de Vision API |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | Resultados de ronda QA y tareas pendientes |

### Registros de Desarrollo y Especificaciones

| Documento | Contenido |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Registro de desarrollo de búsqueda semántica Hailo-10H CLIP |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | Registro de desarrollo de CLIP ONNX multi-backend |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Control de dispositivo Hailo |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Especificación mejorada de registro de chat |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Integración de escritorio Tauri |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Especificación de extensión Freeze & Pull-back |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Plan de metadatos de video v2 (Borrador) |

## Rutas de Importación

Todas las importaciones utilizan directamente rutas de módulos reales. El mecanismo de alias ha sido eliminado.

**Ejemplos de rutas principales:**
- `core.services_core.db_api` — Acceso a BD (antiguo `core.db`)
- `core.configuration.api` — Gestión de configuración (antiguo `core.config`)
- `core.extensions_core.runtime` — Runtime de extensión (antiguo `core.extensions`)
- Las nuevas funciones se agregan directamente al directorio `core/<feature>_core/`

## Solución de Problemas y Operaciones

- Guía de depuración: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Errores comunes (heredado): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- Trampas de codificación CJK / 2 bytes: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Error de análisis de corchetes escapados: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Características

| Documento | Estado | Contenido |
|---|---|---|
| [Guía de Integración MCP](features/mcp-integration-guide.md) | Actual | Operar yu_ai_manager desde LLM |
| [NovelAI V4](features/novelai-v4.md) | Actual | Formato de prompt NovelAI V4 y soporte de negativo por personaje |
| [Búsqueda Semántica Hailo](features/hailo-semantic-search.md) | Implementado → Migración ONNX | Instrucciones de implementación Hailo-10H CLIP |
| [Generación Automática de Etiquetas Danbooru](features/danbooru-tag-gen-spec.md) | Implementado (v2.77.0) | WD-Tagger + enfoque de dos etapas VLM |
| [Gestión de Texto y Registro de Chat](features/text-chatlog-management-spec.md) | Actual | Importación de Chatlog y búsqueda FTS |
| [Protocolo QR v1](features/qr-protocol-v1.md) | Actual | Código QR para compartir en LAN |
| [Benchmark de Búsqueda de Expresión Regular](features/regex-search-benchmark.md) | Actual | Rendimiento de Regex |
| [Compatibilidad del Navegador](features/browser-compatibility.md) | Actual | Lista de navegadores compatibles |

## Referencia de API

- [Descripción General de API (Autenticación, CSRF, Límite de Velocidad)](api/README.md)
- [API de Búsqueda](api/search.md)
- [API de Archivos](api/files.md)
- [API de Escaneo](api/scan.md)
- [Eventos SSE](api/events.md)
- [Variables CSS de Tema](api/theming.md)

## Desarrollo de UI Personalizada / Plugin

- [Guía de UI Personalizada](custom-ui/README.md) — Desarrollo de UI personalizada (inicio rápido, diseño, plantillas, avanzado)
- [Guía de Desarrollo de Plugin](plugin-development/getting-started.md) — Introducción al desarrollo de extensiones
- [Referencia de Manifiesto](plugin-development/manifest-reference.md) — Especificación extension.json

## Instalación

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Documentos Históricos

Los siguientes son notas de implementación anterior / registros de corrección rápida (ubicados en `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Instrucciones de depuración de la era v2.5.4
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Propuesta de mejora de etiquetas de modo oscuro (implementado)
- `EXTENSION_DRAFT.md` — Borrador inicial del sistema de extensión (sucesora en plugin-development/)
