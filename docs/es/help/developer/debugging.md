# Manual de depuración

Manual completo que reúne toda la información necesaria para depurar YU AI Manager.
Sirve como guía para que los desarrolladores y agentes de IA investiguen y corrijan bugs de manera eficiente.

---

## Tabla de contenidos

1. [Inicio del servidor](#inicio-del-servidor)
2. [Registros de depuración](#registros-de-depuración)
3. [Ejecución de pruebas](#ejecución-de-pruebas)
4. [Depuración de BD](#depuración-de-bd)
5. [Omisión y prueba de autenticación](#omisión-y-prueba-de-autenticación)
6. [Depuración MCP](#depuración-mcp)
7. [Depuración de frontend](#depuración-de-frontend)
8. [Lista de variables de entorno](#lista-de-variables-de-entorno)
9. [Errores comunes y soluciones](#errores-comunes-y-soluciones)
10. [Depuración de rendimiento](#depuración-de-rendimiento)

---

## Inicio del servidor

### Para verificación (recomendado)

Iniciar sin PIN, con enlace local. Es la forma básica de prueba y depuración.

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

Si `config_test.json` no existe, créalo con el siguiente contenido:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Equivalente a producción (exposición LAN)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Nota**: Con enlace `0.0.0.0`, el PIN es obligatorio. Desde v4.8.1, el indicador `--debug` se ignora al exponer en LAN (para prevenir fugas de stack trace).

### Reglas de selección de puerto

5100 → 5200 → 5300 → incrementos de 100 en adelante. Verificar antes de iniciar:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### Lista de opciones CLI

| Opción | Tipo | Predeterminado | Descripción |
|-----------|-----|----------|------|
| `--db` | ruta | `data/tags.db` | Ruta del archivo SQLite DB |
| `--config` | ruta | `config.json` | Ruta del archivo de configuración |
| `--host` | str | `127.0.0.1` | Dirección de enlace |
| `--port` | int | 5000 | Puerto de enlace |
| `--lan` | indicador | - | Enlazar a `0.0.0.0` (exponer en LAN) |
| `--pin` | str | - | Habilitar autenticación PIN |
| `--debug` | indicador | - | Habilitar modo debug de Quart |
| `--debug-log` | `on`/`off` | - | Habilitar/deshabilitar registros de depuración estructurados |
| `--debug-log-file` | ruta | `logs/debug.log` | Destino del archivo de registro |
| `--debug-log-max-mb` | int | 10 | Tamaño de rotación del archivo de registro (MB) |
| `--debug-log-backups` | int | 5 | Número de generaciones de copia de seguridad de registros |
| `--debug-log-stdout` | `on`/`off` | `on` | También mostrar registros en stderr |
| `--allow-restart` | indicador | - | Habilitar `/api/server/restart` |
| `--trusted-proxy-auth` | indicador | - | Habilitar autenticación Trusted Proxy |
| `--profile` | str | - | Nombre del perfil de inicio |

### launch-args.txt

Si colocas `launch-args.txt` en el directorio raíz del proyecto, los argumentos escritos en él se cargarán automáticamente al iniciar. Los argumentos CLI tienen prioridad.

---

## Registros de depuración

### Habilitación

```bash
# Habilitar desde CLI
python web_ui.py --db ./tags.db --debug-log on

# Habilitar con variable de entorno
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Formato de registro

Registros de depuración estructurados (función `dlog()` en `core/infra_core/debug_log.py`):

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Formato: `[DEBUG] timestamp | source | event_name | key=value, ...`

### Monitoreo en tiempo real

```bash
# Tail del archivo
tail -f logs/debug.log

# Obtener vía API
curl http://127.0.0.1:5100/api/debug/logs

# Streaming SSE
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### Buffer circular de registros

Los registros en ejecución también se guardan en un buffer circular en memoria (máximo 1000 entradas). Se borran al reiniciar el servidor, así que usa los registros en archivo si necesitas persistencia.

---

## Ejecución de pruebas

### Pruebas unitarias

```bash
source venv/Scripts/activate

# Ejecutar todas las pruebas
python -m pytest tests/test_basic.py -v

# Solo pruebas específicas
python -m pytest tests/test_basic.py::TestImports -v

# Detener inmediatamente al fallar
python -m pytest tests/test_basic.py -x
```

### Pruebas de integración de API

```bash
python -m pytest tests/api/ -v
```

### Pruebas de navegador Playwright

```bash
# 1. Iniciar servidor de verificación
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Ejecutar pruebas
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### Política de pruebas

1. Ejecutar las pruebas primero para entender los fallos actuales
2. Revisar las capturas de pantalla de las pruebas que fallaron
3. Mantener las correcciones al mínimo
4. Volver a probar después de corregir para confirmar

---

## Depuración de BD

### Verificar versión del esquema

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Verificación de integridad de BD

```bash
python db_health.py --db ./tags.db
```

Verifica la existencia de tablas, versión del esquema, restricciones de clave foránea e índices.

### Ejecución de depuración de consultas SQL

Solo disponible si se inicia con `YU_DEBUG_MODE=1`.

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **Nota**: Desde v4.8.1, solo se permiten instrucciones SELECT.

### Consultas de investigación frecuentes

```sql
-- Número de archivos (por fuente)
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Ranking de uso de modelos
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Etiquetas huérfanas
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Detección de rutas duplicadas
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### Distinción de conexiones de BD

| Función | Uso | Cuándo usar |
|------|------|---------|
| `get_readonly_db()` | Solo lectura | APIs GET, búsqueda, estadísticas |
| `get_db()` | Escritura habilitada (con Row factory) | APIs POST/PUT/DELETE |
| `get_raw_db()` | Escritura habilitada (sin Row factory) | Procesamiento en lote, escaneo, migraciones |

> **Importante**: Usar `get_db()` en APIs de solo lectura provoca conflictos de bloqueo de escritura durante el escaneo. Siempre usar `get_readonly_db()`.

---

## Omisión y prueba de autenticación

### Omitir autenticación PIN

Iniciando con `config_test.json` (sin PIN configurado) se omite toda la autenticación.

### Prueba de clave API

```bash
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### Alcance de la clave API

Desde v4.8.1, las claves sin alcance configurado solo permiten **lectura**. Las operaciones de escritura requieren claves con alcance explícito.

| Alcance | Operaciones permitidas |
|---------|--------------|
| `read` | Búsqueda, detalles de archivo, miniaturas, estadísticas |
| `rate` | Establecer/obtener/lote de puntuaciones |
| `tag.write` | Agregar/eliminar etiquetas |
| `collection.write` | CRUD de colecciones, favoritos |
| `annotate` | Lectura/escritura de anotaciones |
| `scan` | Iniciar/cancelar/reanudar escaneo |
| `admin` | Gestión de claves API, cambios de configuración, copia de seguridad/restauración |

---

## Depuración MCP

### Iniciar servidor MCP

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Habilitación de herramientas de depuración

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Configuración de Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "<directorio raíz del proyecto>",
      "env": {
        "YU_API_KEY": "sk_...",
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_DEBUG_MODE": "1"
      }
    }
  }
}
```

### Lista de herramientas de depuración MCP

Con `YU_DEBUG_MODE=1` se registran 9 herramientas de depuración adicionales:

| Herramienta | Uso |
|--------|------|
| `debug_health_check` | Verificación de estado del servidor, BD, tablas |
| `debug_validate_counts` | Comparación de estadísticas API con números reales de BD |
| `debug_validate_search` | Verificación de regresión de API de búsqueda |
| `debug_validate_collection` | Consistencia interna del conteo de colecciones |
| `debug_validate_annotations` | Consistencia de la tabla de anotaciones |
| `debug_sample_files` | Muestreo aleatorio para análisis de completitud de campos |
| `debug_roundtrip_test` | Prueba de ida y vuelta de anotación/puntuación/etiqueta |
| `debug_readonly_query` | Ejecución de consulta SELECT arbitraria |
| `debug_full_report` | Informe integrado de todas las herramientas de observación (1-5) |

---

## Depuración de frontend

### Compilación TypeScript

```bash
pnpm run build        # Empaquetar con esbuild
pnpm run typecheck    # tsc --noEmit (solo verificación de tipos)
```

### Motor SSE compartido

`window.EventSource` está sobreescrita con un Proxy, y usar directamente `new EventSource()` produce un error.

```javascript
// Uso correcto
window.sseSubscribe('scan.progress', (d) => console.log(d.data));
```

### Depuración i18n

```javascript
// Cambiar idioma
window.setLang('en');

// Verificar clave de traducción
console.log(window.tr('search.count.normal', { count: 5 }));
```

Archivos i18n: `ui/default/static/i18n/{lang}.json`

---

## Lista de variables de entorno

### Depuración y registros

| Variable | Valor | Predeterminado | Descripción |
|------|-----|----------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Habilitar/deshabilitar registros de depuración estructurados |
| `TAGDB_DEBUG_LOG` | ruta | `logs/debug.log` | Ruta del archivo de registro |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | Tamaño de rotación del registro (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | Número de generaciones de copia de seguridad |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | Mostrar registros en stderr |

### Servidor

| Variable | Valor | Descripción |
|------|-----|------|
| `TAGDB_DB` | ruta | Ruta del archivo DB |
| `TAGDB_CONFIG` | ruta | Ruta de config.json |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | Habilitar API de reinicio |

### MCP

| Variable | Valor | Descripción |
|------|-----|------|
| `YU_DEBUG_MODE` | `1` | Registrar 9 herramientas de depuración adicionales |
| `YU_BASE_URL` | URL | URL base para el cliente MCP |
| `YU_API_KEY` | `sk_...` | Clave API para el cliente MCP |

---

## Errores comunes y soluciones

### Inicio del servidor

| Error | Causa | Solución |
|--------|------|------|
| `Address already in use` | Puerto ocupado | Especificar otro puerto con `--port 5200` |
| `database is locked` | Conflicto de bloqueo de BD | Verificar que la BD no esté en una ruta de red |
| `--pin is required` | PIN no configurado con enlace LAN | Configurar con `--pin <digit>` |
| `ModuleNotFoundError` | venv no activado o paquetes faltantes | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Autenticación

| Error | Causa | Solución |
|--------|------|------|
| Pantalla PIN se muestra repetidamente | Error de configuración de cookie | Verificar cookies del navegador (DevTools → Application) |
| `CSRF header missing` (403) | Encabezado `X-Requested-With` faltante | Agregar el encabezado al fetch |
| Clave API rechazada | Alcance insuficiente | Desde v4.8.1, las claves sin alcance son solo lectura |

### BD

| Error | Causa | Solución |
|--------|------|------|
| `no such table: schema_version` | Primer inicio | Se genera automáticamente, ignorar |
| Fallo de migración | Bug en el script | Verificar consistencia con `db_health.py` |
| `SQLITE_BUSY` (timeout) | Transacción de larga duración | Verificar si la API de lectura está usando `get_db()` |

### TypeScript

| Error | Causa | Solución |
|--------|------|------|
| Los cambios no se reflejan | No se compiló | `pnpm run build` |
| Error de tipo | Inconsistencia de definición de tipo | Verificar con `pnpm run typecheck` |
| Error de `EventSource` | Se usó new directamente | Usar `window.sseSubscribe()` |

---

## Depuración de rendimiento

### El visor se bloquea durante el escaneo

**Síntoma**: La visualización de imágenes se detiene 5-10 segundos durante el escaneo

**Causa**: La API de lectura estaba usando `get_db()` (conexión que permite escritura)

**Solución**: Siempre usar `get_readonly_db()` en las APIs de solo lectura

### Verificación del límite de tasa

| Nivel | Objetivo | Límite |
|--------|------|------|
| **HEAVY** | Búsqueda similar, cálculo de hash, análisis IA, escaneo | ~20 solicitudes/min (ráfaga 5) |
| **DESTRUCTIVE** | purge, hard-delete, limpieza de caché, escritura de configuración | ~12 solicitudes/min (ráfaga 3) |
| **WRITE** | Otros POST/PUT/DELETE | ~120 solicitudes/min (ráfaga 30) |
| GET | Lectura | Sin límite |

Si se devuelve 429, verificar el encabezado `Retry-After`.
