# Índice de documentación de desarrollo

Lista de documentos de diseño interno, materiales técnicos y registros de desarrollo.
Todos los archivos se encuentran en `docs/development/development_docs/`.

También pueden leerse directamente con la herramienta `source_read` de MCP.

---

## Diseño y arquitectura

| Documento | Contenido |
|-------------|------|
| DESIGN_PHILOSOPHY | Filosofía de diseño — Política general y criterios de decisión del proyecto |
| MODULE_ORGANIZATION_GUIDELINES | Directrices de organización de módulos |
| CODE_SIZE_GUIDELINES | Directrices de tamaño de código (criterios de división de archivos) |
| ENTRYPOINT_MAP | Lista de puntos de entrada |
| DOCUMENT_LIFECYCLE | Política del ciclo de vida de documentos |
| UI_STATE_SPEC | Especificación de estado de UI (híbrido Explorer/Library) |
| NOTIFICATION_PROGRESS_DESIGN | Política de diseño de notificaciones y visualización de progreso |

## API y procesamiento en lote

| Documento | Contenido |
|-------------|------|
| API_RESPONSE_GUIDELINES | Directrices de formato de respuesta de API |
| BATCH_API_STANDARD | Especificación estándar de API en lote |
| ERROR_HANDLING | Política de manejo de errores |

## Sistema de extensiones

| Documento | Contenido |
|-------------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | Especificación del modelo de seguridad de separación de tres poderes |
| EXTENSION_SANDBOX_SPEC | Especificación de Sandbox y permisos |
| EXTENSION_HOOKS_SPEC | Especificación de hooks de extensiones |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Especificación del generador Freeze & Pull-back |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Especificación de migración Core → Extension |

## Integración de IA y agentes

| Documento | Contenido |
|-------------|------|
| AGENT_INTEGRATION_DESIGN | Guía de diseño de integración de agentes de IA |
| AGENT_SAFETY_GATEWAY_SPEC | Especificación del AI Agent Safety Gateway |
| AI_ANALYSIS_LANGUAGE | Especificación de idioma de respuesta del análisis de IA |
| MCP_DEBUG_TOOLS | Especificación de herramientas de depuración MCP |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Problemas y soluciones en la integración Ollama/VLM |
| OPENAI_COMPAT_API_DEVLOG | Registro de desarrollo de API compatible con OpenAI |
| VLM_ROUTING_OCR_SPEC | Especificación de diseño de enrutamiento de modelos VLM y OCR |
| VISION_API_IMAGE_FORMATS | Tabla de compatibilidad de formatos de imagen de Vision API |
| ai-driven-development-principles | Principios de diseño del desarrollo impulsado por IA |

## Base de datos y rendimiento

| Documento | Contenido |
|-------------|------|
| SQLITE_READONLY_SEPARATION | Patrón de separación de lectura/escritura de SQLite |
| LARGE_SCALE_QUERY_OPTIMIZATION | Optimización de consultas en BD de gran escala (280K archivos) |

## Frontend e interfaz de usuario

| Documento | Contenido |
|-------------|------|
| UI_AUDIT_GUIDE | Guía de auditoría completa de UI |
| UI_BUTTON_PRIORITY_GUIDELINES | Directrices de prioridad de botones (método controlador GC) |
| REUSABLE_UI_WIDGETS | Guía de integración de widgets de UI reutilizables |
| VIRTUAL_SCROLL_PITFALLS | Precauciones y bugs conocidos del scroll virtual |
| IMAGE_DISPLAY_OPTIMIZATION | Materiales técnicos de optimización de visualización de imágenes |
| MODAL_LOADING_OPTIMIZATION | Materiales técnicos de aceleración de carga de modales de detalles |
| MODAL_MEDIA_LIFECYCLE | Gestión del ciclo de vida de medios en modales |
| CONTAINER_VIEW_PERFORMANCE | Optimización de rendimiento de vista de contenedor |
| BROWSER_CONNECTION_SATURATION | Desaparición de resultados de búsqueda por saturación de conexiones del navegador |

## Procesamiento de video

| Documento | Contenido |
|-------------|------|
| VIDEO_STREAMING_ARCHITECTURE | Arquitectura de streaming de video |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Registro completo de la optimización de rendimiento de video |
| VIDEO_METADATA_V2_PLAN | Plan de metadatos de video v2 (borrador) |

## Procesamiento de archivos y archivos comprimidos

| Documento | Contenido |
|-------------|------|
| NESTED_ZIP_HANDLING | Diseño y problemas del manejo de ZIP anidado |
| ZIP_SCAN_PERFORMANCE | Optimización de rendimiento del escaneo ZIP/7z |
| ENCODING_FALLBACK | Fallback de codificación de nombres de archivos en archivos comprimidos |
| SD_NAI_PROMPT_SYNTAX_SPEC | Especificación de sintaxis de prompts SD/NAI |

## Multiplataforma e infraestructura

| Documento | Contenido |
|-------------|------|
| CROSS_PLATFORM_ISSUES | Guía de diferencias entre plataformas |
| DRAG_TO_SHARE_CROSS_PLATFORM | Compatibilidad multiplataforma de arrastrar y soltar |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | Corrección del bloqueo del bucle de eventos asyncio |
| MODULE_SAFETY | Diseño de carga segura de módulos |
| DOCKER_SETUP | Guía de configuración del entorno Docker |
| TAURI_DESKTOP_APP | Guía de desarrollo de aplicación de escritorio Tauri |

## Migración

| Documento | Contenido |
|-------------|------|
| QUART_MIGRATION_DEVLOG | Materiales técnicos de migración Flask → Quart (ASGI) |
| CHATLOG_ENHANCED_SPEC | Especificación de registros de chat mejorados |

## Pruebas y control de calidad

| Documento | Contenido |
|-------------|------|
| FUZZ_BURN_IN_TEST | Guía de pruebas Fuzz/Burn-in |
| QA_HANDOFF | Informe de traspaso de calidad |
| yu-ai-manager-qa-agent-prompt | Prompt del sistema del agente QA |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Guía de puntos de accidente frecuentes y velocidad de capa común |
| BUG_VIDEO_AI_ANALYZED_FILTER | Registro de bug: video + filtro analizado por IA |

## Lanzamiento y traducción

| Documento | Contenido |
|-------------|------|
| RELEASE_PROCEDURE | Procedimiento de lanzamiento |
| TRANSLATION_STYLE_GUIDE | Guía de estilo de traducción japonés-inglés |
