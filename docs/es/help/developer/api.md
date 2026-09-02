# Resumen de la API

YU AI Manager proporciona una API REST que permite ejecutar todas las operaciones de la WebUI de forma programática.
Con más de 320 endpoints, cubre operaciones desde la gestión de imágenes hasta el análisis de IA.

> **Consejo**: Para las convenciones comunes detalladas (autenticación, CSRF, límites de tasa, formatos de respuesta), consulta la sección "Referencia de la API".

## Autenticación

Soporta 4 métodos de autenticación.

| Método | Uso | Encabezado/Parámetro |
|------|------|-------------------|
| Autenticación PIN | Sesión del navegador | Iniciar sesión en `/_pin` → cookie de sesión |
| Clave API | Comunicación entre máquinas, MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | Proxy inverso | Encabezado `X-Remote-User` |
| Token LAN Share | Acceso de invitado | Ruta `/s/<token>` |

### Ejemplo de prueba con curl

```bash
# Autenticación con clave API (sin encabezado CSRF necesario)
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# En entornos con autenticación PIN se necesitan 2 pasos
# 1. Obtener token CSRF
curl -c cookies.txt http://localhost:5000/_pin
# 2. Enviar PIN
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### Protección CSRF

Es obligatorio incluir el encabezado `X-Requested-With` en todos los endpoints POST/PUT/DELETE de `/api/`.
No es necesario en solicitudes con clave API Bearer.

## Endpoints principales

### Búsqueda y navegación de imágenes

| Método | Ruta | Descripción |
|---------|------|------|
| GET | `/api/search` | Búsqueda filtrada por etiquetas, fecha, puntuación, etc. |
| GET | `/api/search-grouped` | Búsqueda agrupada por carpeta/ZIP |
| GET | `/api/file/<id>` | Obtener metadatos detallados de una imagen |
| GET | `/api/thumbnail/<id>` | Obtener miniatura (WebP, caché ETag) |
| GET | `/api/original/<id>` | Obtener imagen original (compatible con solicitudes Range) |
| GET | `/api/suggest` | Candidatos de autocompletar de etiquetas |

### Puntuaciones, etiquetas y anotaciones

| Método | Ruta | Descripción |
|---------|------|------|
| POST | `/api/ratings/batch-set` | Establecer puntuaciones en lote |
| POST | `/api/tags/batch-set` | Edición de etiquetas en lote |
| POST | `/api/annotations/batch-set` | Establecer anotaciones en lote |
| GET | `/api/annotations/<id>` | Obtener anotaciones |
| GET | `/api/annotations/search` | Buscar anotaciones |

### Colecciones

| Método | Ruta | Descripción |
|---------|------|------|
| GET | `/api/collections` | Lista de colecciones |
| POST | `/api/collections` | Crear colección |
| PUT | `/api/collections/<id>` | Cambiar nombre de colección |
| DELETE | `/api/collections/<id>` | Eliminar colección |
| POST | `/api/collections/<id>/batch-add` | Agregar archivos en lote |
| POST | `/api/collections/<id>/batch-remove` | Eliminar archivos en lote |

### Escaneo

| Método | Ruta | Descripción |
|---------|------|------|
| POST | `/api/scan/start` | Iniciar escaneo |
| GET | `/api/scan/status` | Obtener progreso del escaneo |
| POST | `/api/scan/cancel` | Cancelar escaneo |
| POST | `/api/scan/resume` | Reanudar escaneo interrumpido |
| GET | `/api/scan-roots` | Lista de raíces de escaneo |
| POST | `/api/scan-roots` | Agregar raíz de escaneo |

### Análisis de IA

| Método | Ruta | Descripción |
|---------|------|------|
| POST | `/api/analysis/analyze/<id>` | Ejecutar análisis de IA de imagen |
| GET | `/api/analysis/result/<id>` | Obtener resultado del análisis |
| POST | `/api/analysis/batch` | Análisis en lote |
| POST | `/api/wd-tagger/tag/<id>` | Inferencia WD-Tagger |
| POST | `/api/wd-tagger/batch` | Inferencia en lote de WD-Tagger |
| POST | `/api/analysis/batch/cancel` | Cancelar lote de análisis de IA |
| POST | `/api/wd-tagger/batch/cancel` | Cancelar lote de WD-Tagger |
| POST | `/api/tagger-servers/batch/cancel` | Cancelar lote del clúster de etiquetado |
| POST | `/api/ocr/<id>` | Ejecutar OCR |

### Configuración

| Método | Ruta | Descripción |
|---------|------|------|
| GET | `/api/settings/schema` | Obtener esquema de configuración |
| GET | `/api/settings/all` | Obtener todos los valores de configuración |
| GET | `/api/settings/<key>` | Obtener valor de configuración |
| PUT | `/api/settings/<key>` | Actualizar valor de configuración |

### Gestión de extensiones

| Método | Ruta | Descripción |
|---------|------|------|
| GET | `/api/extensions` | Lista de extensiones |
| POST | `/api/extensions/<name>/toggle` | Habilitar/deshabilitar |
| POST | `/api/extensions/install` | Instalar desde repositorio Git |
| DELETE | `/api/extensions/<name>/uninstall` | Desinstalar |

### Mecanismo de seguridad para agentes

| Método | Ruta | Descripción |
|---------|------|------|
| POST | `/api/agent/kill` | Activar Kill Switch |
| POST | `/api/agent/resume` | Desactivar Kill Switch |
| GET | `/api/agent/status` | Estado del mecanismo de seguridad |
| GET | `/api/agent/journal` | Diario de operaciones |
| POST | `/api/agent/undo/<journal_id>` | Deshacer operación |

## Formato de respuesta

Todas las APIs responden en un formato JSON unificado.

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

En caso de error:

```json
{
  "ok": false,
  "data": null,
  "error": "Mensaje de error"
}
```

## Límite de tasa

Sistema de cubo de tokens de 3 niveles.

| Nivel | Objetivo | Límite | Ráfaga |
|--------|------|------|---------|
| READ | Todas las solicitudes GET | Sin límite | - |
| WRITE | POST/PUT/DELETE | ~120 solicitudes/min | 30 |
| HEAVY | Búsqueda similar, análisis IA, escaneo | ~20 solicitudes/min | 5 |
| DESTRUCTIVE | purge, hard-delete, escritura de configuración | ~12 solicitudes/min | 3 |

Cuando se supera el límite se devuelve HTTP 429. Verificar el encabezado `Retry-After` para el tiempo de espera en segundos.

## SSE (Server-Sent Events)

Los eventos en tiempo real se distribuyen desde `/api/events/stream` mediante SSE.
Para más detalles, consultar la sección "Eventos SSE".

> **Nota**: Máximo 10 conexiones simultáneas por IP. El límite de tamaño de carga útil es 100 MB.

## Documentación de diseño interno

Los detalles sobre las decisiones de diseño de la API, la optimización del rendimiento de SQLite, el diseño del esquema de BD y otros conocimientos de desarrollo se pueden ver en el [Visor MD](/ext/md-viewer/).
