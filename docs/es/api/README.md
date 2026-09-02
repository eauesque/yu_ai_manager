# Referencia de API de YU AI Manager

Esta documentación de API REST cubre todas las características de YU AI Manager, disponibles para interfaces de usuario personalizadas y scripts.

## Convenciones Comunes

### URL Base

```
http://<host>:<port>
```

Predeterminado: `http://127.0.0.1:5000`
Entorno de prueba: `http://127.0.0.1:5100` (al usar `config_test.json`)

### Autenticación

Se admiten cuatro métodos de autenticación:

| Método | Caso de Uso | Ejemplo de Encabezado |
|--------|----------|----------------|
| PIN Auth | Sesiones de navegador | Cookie: `session=...` |
| API Key | Comunicación máquina a máquina | `Authorization: Bearer sk_...` |
| Trusted Proxy | Detrás de un proxy inverso | `X-Remote-User: username` |
| LAN Share Token | Acceso de invitado | Ruta URL `/s/<token>/...` |

Es posible omitir la autenticación completamente lanzando con `config_test.json` (sin PIN).

### Protección CSRF

Todas las solicitudes `POST` / `PUT` / `DELETE` a los endpoints `/api/` requieren el encabezado `X-Requested-With`:

```
X-Requested-With: XMLHttpRequest
```

**Excepción**: Las solicitudes de API Key con el encabezado `Authorization: Bearer` no requieren CSRF.

### Limitación de Velocidad

| Nivel | Alcance | Velocidad | Ráfaga |
|------|-------|------|-------|
| READ | Todos GET | Ilimitado | - |
| WRITE | POST/PUT/DELETE (estándar) | ~120 req/min | 30 |
| HEAVY | Búsqueda similar, cálculo de hash, análisis de IA, escaneo | ~20 req/min | 5 |
| DESTRUCTIVE | Purga, eliminación dura, borrado de caché, escritura de configuración | ~12 req/min | 3 |

Un encabezado `Retry-After` acompaña las respuestas 429.

### Formato de Respuesta

**Éxito** (nuevas APIs):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**Error**:
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE",
  "detail": "Additional details (optional)"
}
```

Algunas API legadas devuelven el formato `{ "success": true, "message": "..." }`.

### Paginación

**Basada en offset** (predeterminada):
```
GET /api/search?offset=0&limit=50
```

**Basada en cursor** (para conjuntos de datos grandes):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

La respuesta incluye un campo `next_cursor`.

### Operaciones por Lotes

Las APIs por lotes admiten hasta 500 operaciones por solicitud. El éxito parcial es posible:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## Categorías de API

| Documento | Contenido |
|----------|---------|
| [search.md](search.md) | Búsqueda, sugerencias, grupos |
| [files.md](files.md) | Detalles de archivo, miniaturas, recuperación de medios |
| [scan.md](scan.md) | Control de escaneo, gestión de raíz de escaneo |
| [events.md](events.md) | Flujo de eventos SSE |
| [theming.md](theming.md) | Variables CSS, personalización de tema |
| [source.md](source.md) | Navegación de código fuente (solo lectura para MCP) |
| [github.md](github.md) | Integración de GitHub (cuentas, problemas, PRs, notificaciones, discusiones, lanzamientos) |
| [scheduler.md](scheduler.md) | Programador de Tareas (gestión de trabajos, historial de ejecución) |
| [ratings.md](ratings.md) | Calificaciones (establecer, establecer por lotes, obtener, estadísticas) |
| [favorites.md](favorites.md) | Favoritos (alternar, verificar, listar) |
| [collections.md](collections.md) | Colecciones (CRUD, reordenar, agregar/eliminar por lotes, exportación CSV) |
| [tags.md](tags.md) | Etiquetas (establecer por lotes, sugerir) |
| [sns.md](sns.md) | Compartir SNS y Monitor de Bluesky (publicación, notificaciones, clasificación, respuesta automática) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (configuración, etiquetado único/lotes, CRUD de etiquetas) |
| [tagger-servers.md](tagger-servers.md) | Registro del Servidor de Etiquetador (clúster de inferencia de etiquetado distribuido, gestión de servidores, ejecución por lotes) |
| [svg.md](svg.md) | Rasterización de SVG (conversión de SVG a PNG/WebP, soporte de canalización img2img) |
| [settings.md](settings.md) | Gestión de Configuración (esquema, obtener/actualizar valores, cifrado de secretos, integración 1Password/Bitwarden) |
| [extensions.md](extensions.md) | Extensiones (listar, alternar, configurar, instalar, seguridad, mercado, autoría) |
| [analysis.md](analysis.md) | Análisis de IA (configuración, análisis único/lotes, análisis de tendencias, estadísticas, registro de servidor) |
| [system-update.md](system-update.md) | Actualización de Sistema (verificación de versión, aplicar actualización, gestor de actualización unificado) |
| [tools.md](tools.md) | Herramientas (detección de duplicados, cálculo de hash, búsqueda similar, gestión de caché, copia de seguridad, limpieza de archivo) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch, Circuit Breaker, Budget, Approval, Scope Fence, Undo, Anomaly Detection) |
| [profiles.md](profiles.md) | Gestión de Perfil (CRUD, duplicado, exportación/importación de código QR) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (etiquetado automático de Danbooru, gestión de modelos, VLM, XMP) |
| [ocr.md](ocr.md) | OCR (reconocimiento de texto, traducción, soporte de video/PDF, puntos de referencia, perfiles) |
| [apikeys.md](apikeys.md) | Gestión de Claves API (crear, listar, alcances, revocar) |
| [debug.md](debug.md) | Depuración (inspección de metadatos, consulta SQL, verificación de modelos) |
| [ui.md](ui.md) | Gestión de UI (listar, cambiar, instalar, desinstalar) |
| [video-analysis.md](video-analysis.md) | Análisis de Vídeo (configuración, estado, extracción de fotogramas clave) |

## Inicio Rápido (curl)

```bash
# Búsqueda (entorno sin PIN)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# Recuperar una miniatura
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# Búsqueda con Clave API
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# Establecer una calificación
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```
