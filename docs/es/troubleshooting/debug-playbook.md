# Guía de depuración de YU AI Manager

## Inicio rápido

```bash
# Ejecutar todo el diagnóstico
python debug_check.py

# Especificando BD
python debug_check.py --db /path/to/tags.db

# Comprobación rápida (omite sintaxis / Extensions)
python debug_check.py --quick
```

---

## Problemas frecuentes y soluciones

### 1. config.json se ha corrompido (problema de barras invertidas)

**Síntoma:** JSONDecodeError al arrancar el servidor
**Causa:** Al introducir rutas de Windows a mano, `\U`, `\w`, etc., quedan mal escapados
**Solución:** Se repara automáticamente al arrancar el servidor. Para repararlo a mano:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. En scan-all se omite alguna carpeta

**Síntoma:** En "Escanear todas las carpetas", alguna carpeta no se procesa
**Pasos de verificación:**
```bash
# Verificar el contenido de scan_roots
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Puntos a comprobar:**
- ¿La ruta no es demasiado corta (no es solo `\\wsl.localhost\`)?
- ¿No hay un `\` al final?
- ¿`os.path.exists(path)` devuelve True?

### 3. En "Compartir QR" aparece "sin contenido"

**Síntoma:** Botón Compartir QR → Positive/Negative vacíos
**Posibles causas:**
1. No hay registro en la tabla `templates` (meta_source=unknown)
2. Discordancia de claves en la respuesta de la API (corregida en v2.7.0)

**Verificación:**
```bash
# Comprobar si existe template para el ID del archivo
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # ID problemático
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Fallo de escaneo con rutas WSL/UNC

**Síntoma:** El probe falla con rutas `\\wsl.localhost\...`
**Verificación:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**Nota:** `pathlib.Path.exists()` tiene un bug con rutas UNC de WSL. Use `os.path.exists()`.

### 5. Las extensiones no se cargan

**Síntoma:** No aparecen en la lista de extensiones
**Verificación:**
```bash
python debug_check.py  # mire la sección de verificación de Extensions
```
**Puntos a comprobar:**
- ¿Existe `extension.json` o `extension.yml`?
- ¿El JSON/YAML es válido (compruebe con `safe_load_config`)?
- ¿Existe el campo `name`?

### 6. Bloqueo por autenticación PIN

**Síntoma:** 5 fallos → bloqueo de 60 s
**Solución:** Espere 60 s. O reinicie el servidor para restablecer.
**Verificación:** Herramientas de desarrollador del navegador → Network → respuesta de `/_pin_check` para ver el mensaje de error

### 7. Quiero verificar QR / Bundle del reporte de bug de la página de error 500

**Síntoma:** Toda la página devuelve 500 y se muestra la página de error específica
**Alcance:** Excepciones no manejadas del servidor, fallo global de la página HTML

**Elementos mínimos a verificar:**
- Se muestra un código QR en pantalla
- Se muestra el botón `Copiar JSON del Bundle`
- Se muestra el botón `Descargar Bundle (.json.gz)`
- Al abrir el QR, en `docs/bugreport.html` se ve `AI Error Bundle`

**Pasos de verificación:**
```bash
# Primero arrancar el servidor normal
venv\Scripts\python.exe web_ui.py
```

1. En el navegador provoque una operación que genere 500 intencionalmente
2. Verifique que en la página de error 500 aparecen el QR y los botones del Bundle
3. Pulse `Copiar JSON del Bundle` y compruebe que el JSON contiene `schema`, `error_id`, `request`, `error`, `state`
4. Pulse `Descargar Bundle (.json.gz)` y verifique que se guarda un `err_*.json.gz`
5. Lea el QR con el móvil, o abra la URL del QR para llegar a `bugreport.html`
6. Verifique que en la relay page se ve el texto completo del `AI Error Bundle` y que al generar un GitHub Issue ese JSON entra en el cuerpo

**Puntos a observar:**
- ¿`bundle.error.class` y `bundle.error.message` no están vacíos?
- ¿`bundle.request.path` coincide con la URL real del fallo?
- ¿`bundle.error.frames` contiene file/line/function del punto de fallo?
- ¿No faltan `bundle.state.server_info` y `bundle.state.extensions`?
- Si el QR es demasiado largo, ¿la relay page puede decodificarlo?

**Triaje:**
- Aparece el QR pero la relay page falla al decodificar
  Verifique pack/shrink en `core/web/error_bundle.py` y el decode gzip en `docs/bugreport.html`
- No aparecen los botones Copy/Download
  Verifique en `core/web/error_handlers.py` que `bundle_json` / `bundle_download_b64` se pasan a la plantilla
- Solo falla la descarga
  Verifique el base64 decode y la creación del Blob `application/gzip` en `ui/default/templates/error.html`

**Archivos relacionados:**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`
- `docs/bugreport.html`
- `docs/ja/features/qr-protocol-v1.md`

### 8. Verificar el client error reporter cuando falla solo parte de la página

**Síntoma:** La página completa se abre, pero fallan solo tarjetas, secciones o cargas de API
**Alcance:** 4xx/5xx de `fetch`, errores de red, `window.error`, `unhandledrejection`, fallo del loader de la tools page

**Elementos mínimos a verificar:**
- Aparece el launcher del error reporter en la esquina inferior derecha
- Desde el launcher se puede abrir un modal
- En el modal funcionan `Copy JSON` / `Download .json.gz` / `GitHub Issue`
- El bundle incluye `X-Request-Id` y `ui_events`

**Pasos de verificación:**
1. Abra una pantalla que use `apiFetch`
2. Provoque una operación que llame a una API que devuelva 500 o a una API inexistente
3. Verifique que aparece el launcher en la parte inferior derecha
4. Abra el modal y revise el JSON del bundle
5. Verifique que contiene `request.status`, `request.url`, `request.request_id`, `repro.ui_events`
6. Pulse `Download .json.gz` y verifique que guarda el bundle comprimido

**Verificación con herramientas de desarrollador:**
- En la pestaña Network, comprobar que la cabecera de respuesta de la API fallida tiene `X-Request-Id`
- Si hay excepciones no manejadas en la consola, ¿el bundle del launcher contiene el mismo error?
- `/api/error-report/enrich` devuelve 200 y tras enriquecer, ¿el bundle contiene `state.server_info` o `artifacts.recent_logs`?

**Ejemplos de reproducción sencilla:**
- Lanzar una excepción a propósito en el loader de la tools page
- Llamar temporalmente a un endpoint inexistente como `apiFetch('/api/not-found-for-debug')`
- En el servidor, reemplazar temporalmente la ruta objetivo por `api_error(...)` o lanzar excepciones

**Triaje:**
- Está fallando pero no aparece el launcher
  Verifique `src/ts/main/api-utils.ts` o `src/ts/shared/error-reporter.ts`. Probablemente no se pase por el `apiFetch` común
- El bundle no tiene `request_id`
  Verifique en `core/web/request_hooks.py` que `X-Request-Id` se añade a todas las respuestas
- Tras enrich la información del servidor sigue vacía
  Verifique `/api/error-report/enrich` en `routes/server_info.py` y `enrich_error_bundle()` en `core/web/error_bundle.py`
- No se capturan los fallos parciales de la tools page
  Verifique la llamada a `captureThrownError(...)` en `src/ts/tools-page/index.ts`

**Archivos relacionados:**
- `src/ts/shared/error-reporter.ts`
- `src/ts/main/api-utils.ts`
- `src/ts/tools-page/index.ts`
- `src/ts/nav/index.ts`
- `core/web/request_hooks.py`
- `routes/server_info.py`
- `core/web/error_bundle.py`

---

## Cómo leer los logs de depuración

### Salida de consola del servidor

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → Se ejecutó la reparación automática de barras invertidas en config.json

[DEBUG] scan/start: raw=..., sanitized=...
  → Ruta al iniciar el escaneo (valor crudo → tras sanear)

[DEBUG] scan-all root 0: repr=..., len=...
  → Detalle de cada raíz al escanear todas las carpetas

[Scan] Auto-registered scan root: /path/to/dir
  → Registro automático al completar el escaneo

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → API de compartir QR: el archivo existe pero no hay template

[ERROR] file.json: JSON parse failed: ...
  → Error de parseo en safe_load_json (la app no se cae)
```

---

## Estructura de archivos y objetivos de depuración

```
web_ui.py          ← punto de entrada (arranque del servidor)
core/
  config.py        ← gestión de configuración, safe_load_*
  server.py        ← autenticación PIN, QuickLock
  scanner.py       ← motor de escaneo
  extensions.py    ← carga de extensiones
  db.py            ← gestión de conexiones de BD
  schema.py        ← definiciones de tablas
routes/
  scan.py          ← API de escaneo
  search.py        ← API de búsqueda
  share.py         ← API de compartir QR
  tools.py         ← API de herramientas + API Inspect
  debug.py         ← API de depuración
  pages.py         ← enrutamiento de páginas
  server_info.py   ← server-info / API de enrich de reporte de error
core/web/
  error_handlers.py ← página de error 500 + generación del reporte QR de bug
  error_bundle.py   ← generación / reducción / enrich del error bundle
  request_hooks.py  ← asignación de X-Request-Id
ui/default/templates/
  error.html       ← UI Copy / Download de la página 500
static/js/
  main.js          ← UI principal (búsqueda, modal, QR, teclado)
  scan-banner.js   ← progreso de escaneo + scroll-to-top (todas las páginas)
src/ts/shared/
  error-reporter.ts ← client-side error reporter para fallos parciales
```
