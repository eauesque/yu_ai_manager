# Tag Database - Debug Checklist

**Lista de depuración por orden de prioridad**
**Estado**: Legado (registro de la era v2.5.x; todos los puntos ya están resueltos)
**Última actualización**: 2026-02-13

---

## P0 (Critical): corrección inmediata (afecta a la usabilidad)

### ✅ 1. Corrección del desalineamiento del layout de la UI

**Problema:**
```
Los campos de búsqueda no caben en horizontal y
los botones quedan desalineados
```

**Cómo verificarlo:**
1. Arrancar WebUI
2. Redimensionar el navegador a 1366x768
3. Verificar la fila de búsqueda

**Ubicación de la corrección:** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- Añadir flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Verificación:**
- [ ] Se visualiza correctamente a 1920x1080
- [ ] Se visualiza correctamente a 1366x768
- [ ] Se visualiza correctamente a 768x1024 (tableta)

---

### ✅ 2. Eliminación de duplicados en autocompletado de etiquetas

**Problema:**
```
Aparecen duplicados en las sugerencias de autocompletado

Ejemplo de visualización:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ solo difieren en los espacios
```

**Cómo verificarlo:**
1. Escribir "sample_creator" en el campo de etiquetas
2. Observar el autocompletado
3. Comprobar si hay duplicados

**Ubicación de la corrección:** `static/js/main/main.js`
```javascript
// Dentro de initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normalizar y deduplicar
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // espacio tras coma
      .replace(/\s+/g, ' ')        // varios espacios → uno
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Sumar el conteo
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Verificación:**
- [ ] ¿Desaparecen los duplicados?
- [ ] ¿Se suman los conteos?
- [ ] ¿No hay problemas de rendimiento?

---

## P1 (High): mejora (afecta a la funcionalidad)

### ✅ 3. Test de normalización de paréntesis en la búsqueda

**Problema:**
```
Verificar que \(tag\) y (tag) son equivalentes
```

**Cómo verificarlo:**
1. Preparar una imagen con la etiqueta `\(emphasis\)`
2. Buscar `(emphasis)` en la barra
3. Comprobar si aparece

**Puntos a verificar:**
- [ ] Al buscar `(tag)` → también encuentra `\(tag\)`
- [ ] Al buscar `\(tag\)` → también encuentra `(tag)`
- [ ] En modo regex no se aplica la conversión

**Código relacionado:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. Test de lectura de archivos dentro de ZIP

**Problema:**
```
¿Se muestran correctamente las imágenes dentro de ZIP?
¿Se extraen bien los metadatos?
```

**Casos de prueba:**

#### Test 1: Funcionamiento básico
```bash
# 1. Crear ZIP de prueba
zip test.zip image1.png image2.png

# 2. Escanear
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Verificar
python tagdb_tool.py search --db test.db --q "*"
```

**Verificación:**
- [ ] Los archivos dentro del ZIP quedan registrados como `test.zip!image1.png`
- [ ] Los metadatos están extraídos
- [ ] Se muestra la miniatura

#### Test 2: Función de descompresión
```
1. Abrir un archivo dentro del ZIP en WebUI
2. Pulsar el botón "Descomprimir y editar"
3. Comprobar si se abre el explorador
4. Comprobar si existe el archivo descomprimido
```

**Verificación:**
- [ ] Se muestra el botón de descompresión
- [ ] Al hacer clic se abre el explorador
- [ ] Se descomprime en el directorio extracted/
- [ ] El archivo descomprimido queda registrado en la BD

#### Test 3: ZIP de gran tamaño
```bash
# 1) Crear un ZIP de 1,1 GB (Zip64)
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) Escaneo dentro del ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Verificación:**
- [x] ¿El uso de memoria no crece de forma anómala?
- [x] ¿El tiempo de escaneo está en rango aceptable (menos de 5 min)?
- [x] ¿No aparecen errores?

**Medición real (2026-02-17):**
- Tamaño del ZIP: `1,153,433,914 bytes` (~1,1 GB)
- Tiempo de ejecución: `elapsed=0:00.14`
- RSS máximo: `maxrss_kb=23864`
- Registro en BD: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Test de búsqueda de checkpoint

**Problema:**
```
¿Se extrae y busca correctamente el nombre del modelo?
```

**Casos de prueba:**

#### Test 1: Extracción del nombre del modelo
```python
# Verificar que se extrae el nombre en cada formato

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**Verificación:**
- [ ] Se extrae en formato NovelAI
- [ ] Se extrae en formato SD
- [ ] Se extrae en formato ComfyUI

#### Test 2: Función de búsqueda
```
1. Clic en el campo de checkpoint en WebUI
2. ¿Se muestra el autocompletado?
3. Buscar "animagine"
4. ¿Se muestran solo las imágenes de ese modelo?
```

**Verificación:**
- [ ] Funciona el autocompletado
- [ ] Se puede buscar por coincidencia parcial
- [ ] Se ordena por frecuencia de uso

---

## P2 (Medium): actuación futura (mejora de rendimiento)

### ✅ 6. Implementación de caché de miniaturas

**Problema:**
```
La miniatura de archivos dentro de ZIP se genera cada vez
→ lento
```

**Propuesta de implementación:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Generar ruta de caché
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Si hay caché, devolverla
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Si no, generar
    thumbnail = generate_thumbnail(...)

    # Guardar en caché
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Verificación:**
- [ ] Segundo acceso acelerado
- [ ] Uso de disco aceptable
- [ ] Función de limpiar caché

---

### ✅ 7. Medición de rendimiento con grandes volúmenes

**Casos de prueba:**

#### Test 1: 100 000 archivos
```bash
# Medir tiempo de escaneo
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Medir tiempo de búsqueda
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Objetivo:**
- [ ] Escaneo: 50 000 elementos/hora o más
- [ ] Búsqueda: menos de 1 s (entre 100 000)

#### Test 2: Respuesta de WebUI
```
1. Arrancar WebUI con BD de 100 000
2. Ejecutar búsqueda
3. Hacer scroll
```

**Verificación:**
- [ ] Los resultados se muestran en menos de 3 s
- [ ] El scroll es fluido
- [ ] El navegador no se congela

---

## Lista de verificación para ejecutar tests

### Preparación del entorno
- [ ] Verificar Python 3.8+ instalado
- [ ] Instalar dependencias
- [ ] Preparar datos de prueba (imágenes de cada formato)

### Tests funcionales
- [ ] Lectura de ZIP
- [ ] Escaneo de varios directorios
- [ ] Normalización de etiquetas
- [ ] Búsqueda de checkpoint
- [ ] Filtro por modelo

### Tests UI/UX
- [ ] Layout (varias resoluciones)
- [ ] Modo oscuro
- [ ] Atajos de teclado
- [ ] Autocompletado

### Tests de rendimiento
- [ ] 10 000 elementos
- [ ] 50 000 elementos
- [ ] 100 000 elementos
- [ ] ZIP grande (500 MB+)

### Compatibilidad de navegador
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### Compatibilidad de SO
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Herramientas de depuración

### Activar logs
```bash
# Añadir al principio de tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Medición de rendimiento
```python
import time

start = time.time()
# ... proceso ...
print(f"Time: {time.time() - start:.2f}s")
```

### Verificación del uso de memoria
```python
import tracemalloc

tracemalloc.start()
# ... proceso ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Fecha de creación:** 2026-02-13
**Prioridad:** atender en orden P0 → P1 → P2
**Nota:** Esta lista se creó en la era v2.5.x y todos los puntos ya están resueltos
