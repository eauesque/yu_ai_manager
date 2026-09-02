# Trampas de codificación CJK / 2 bytes y contramedidasEste documento resume errores específicos de región 2 bytes, centrado en japonés (CP932/Shift-JIS),
y soluciones adoptadas en este proyecto. Destinado a desarrolladores e IA que encuentren problemas similares.

---

## 1. Bloqueo consola Windows cp932

### Síntoma

Consola Windows `cmd.exe` / PowerShell / Git Bash tiene codificación salida predeterminada **cp932 (Shift-JIS)**.
`print()` caracteres Unicode no en cp932 causa `UnicodeEncodeError` bloqueo inmediato.

```
UnicodeEncodeError: 'charmap' codec can't encode character '—' in position 12
```

### Ejemplo caracteres encontrados

| Carácter | Nombre | Ubicación uso |
|----------|--------|---|
| `—` (U+2014) | em dash | Separador registro |
| `–` (U+2013) | en dash | Pantalla progreso |
| `✓ ✗ ✅ ❌ ⚠️` | marcas/emoji | Éxito/fallo |
| `🧹 📦 📁 🔍 🔧` | emoji | Indicación proceso |
| `█ ░` | caracteres bloque | Barra progreso |

### Contrameida

- **`print()` usa solo caracteres ASCII seguro**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-`, etc.
- `logging` igual. Si handler encoding es cp932, mismo problema
- `PYTHONIOENCODING=utf-8` evita, pero depende entorno usuario. ASCII defensivo más seguro

### Alcance impacto

Proyecto modificó **19 archivos** una vez (v2.28.0).
AI (Claude/GPT) alta probabilidad genera emoji y em dash, **revisión código IA máxima atención**.

---

## 2. Caracteres corrompidos nombre ZIP (CP437 mojibake)

### Síntoma

ZIP antiguo (creado Windows 95/98/XP) almacena nombre archivo **Shift-JIS (CP932)**,
pero especificación ZIP sin información codificación. Python `zipfile` sin flag UTF-8 (bit 11)
decodifica **CP437**, nombres japonés se vuelven `âwâCâèâb` corruptos.

### Contrameida: cadena fallback 10 pasos

`core/infra_core/encoding.py` define lista prioridad codificación CJK:

```
UTF-8 (zipfile intento primero) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- `chardet` / `cchardet` **no usar**: nombres cortos (10-30 bytes) demasiadas inexactitudes
- Orden fijo reproducible, debug fácil

### Parámetro `metadata_encoding` Python 3.11+

```python
# Python 3.11+ specify directamente
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

Solo CP932, intenta sin `metadata_encoding` y fallback `repair_cp437_name()`.

### Caso 7z

7-Zip procesamiento nombre propio. vía CLI 7z
puede ocurrir CP437 mojibake, recuperar similar con `repair_cp437_name()`.

---

## 3. ZIP/7z 2 bytes caracteres bloquea escaneo

### Síntoma

`zipfile.ZipFile()` leyendo directorio central ZIP antiguo CP932
algunas secuencias bytes causa I/O bloqueante cuelga.
Archivos muchos archivos ocurre frecuentemente.

### Contrameida

1. **Protección timeout**: asistente daemon thread `run_with_timeout()`
   - Lista (listing): 30 segundos
   - Escaneo I/O: 60 segundos
2. **Tabla scan_errors** (migration v24): registrar BD persistente timeout/error codificación
   - Clasificación tipo error: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars comillas problema

### Síntoma

SQLite FTS5 `tokenize` directiva `tokenchars` opción,
combinación comillas causa parse error.

```sql
-- NG: comilla simple exterior + comilla doble interior → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK: comilla doble exterior + comilla simple interior
tokenize="unicode61 tokenchars '_:.'"
```

### Causa

Analizador tokenizador FTS5 SQLite
no analiza correctamente comilla doble dentro comilla simple exterior. Diferencia versión SQLite (3.45.1 confirmado).

### Contrameida

Código Python usar tipos triple-quote variar:

```python
# OK: Python ''' contiene SQL " y '
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### Descubrimiento

Reconstrucción tabla FTS5 migration 29 proyecto. Código IA generado uso comilla simple exterior,
SQLite 3.45.1 bloqueo inicio servidor (v2.70.1 reparó).

---

## 5. WebP EXIF codificación UTF-16

### Síntoma

Herramientas generación imagen (especialmente NAI) WebP EXIF metadatos
**UTF-16 (BOM incluido)** encodeados. Decodificación UTF-8 normal corrupción caracteres.

### Contrameida

- Detectar BOM determinar UTF-16 BE/LE
- Sin BOM usar heurística BE/LE estima
- Fallback UTF-8 → latin-1 intento

---

## 6. PNG tEXt chunk codificación

### Síntoma

Especificación PNG tEXt chunk **Latin-1 (ISO-8859-1)** define,
pero herramientas generación imagen IA mayoría UTF-8 almacenan directo.
Decodificar `latin-1` japonés corrupción caracteres.

### Contrameida

Decodificar UTF-8 primero, fallback latin-1 fallo:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. config.json ruta Windows backslash

### Síntoma

Rutas Windows contienen barra invertida (`\`), escribir manualmente
JSON ruta secuencia escape inválida.

```json
{"scan_roots": ["C:\Users\test"]}  // \U y \t secuencia escape
```

### Contrameida

- `_repair_json_backslashes()` repara automáticamente inicio servidor
- Normaliza internamente rutas guardar

---

## 8. pathlib WSL UNC ruta

### Síntoma

WSL (Windows Subsystem Linux) `pathlib.Path.exists()`
UNC ruta (`\\server\share\...`) resultado incorrecto devuelve.

### Contrameida

- Confirmación existencia UNC ruta usar `os.path.exists()`
- `pathlib` conveniente, rutas red confiabilidad baja

---

## 9. CSV exportación UTF-8 BOM

### Síntoma

Archivo CSV UTF-8 abrir Excel, sin BOM corrupción caracteres.
Excel BOM UTF-8 sin como ANSI interpreta (japonés CP932 ambiente).

### Contrameida

```python
buf.write("﻿")  # UTF-8 BOM compatibilidad Excel
```

Agregar BOM (`﻿`) principio CSV.
Excel UTF-8 reconoce correctamente.

---

## 10. JSON `ensure_ascii=False`

### Síntoma

Python `json.dumps()` predeterminado caracteres no-ASCII como `\uXXXX` escapa.
Respuesta herramienta MCP nombres etiqueta japonés rutas archivos `タグ`
escape, agente IA contenido entienda difícil.

### Contrameida

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

Proyecto usa todo módulo herramienta MCP (10 archivos) uniformemente.

---

## 11. Salida decodificación diálogo selección carpeta

### Síntoma

PowerShell Windows diálogo selección carpeta llamar, `subprocess`
salida CP932 codificada. Decodificación UTF-8 predeterminado `UnicodeDecodeError`.

### Contrameida

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` decodificación fallo procesado seguramente.

---

## Notas agentes IA

Muchos problemas anteriores **IA genera código tiende pasar por alto** patrón:

1. **`print()` emoji/caracteres decoración no usar** — IA tiende incluso mejorar apariencia
2. **No asumir codificación nombre archivo** — UTF-8 asume CP932 ambiente rompe
3. **SQLite comillas prueba máquina necesaria** — Documento acuerdo no funciona casos
4. **`json.dumps()` `ensure_ascii=False`** — Datos japonés manejo obligatorio
5. **subprocess salida entorno codificación decodificar** — Windows CP932 mayormente
6. **CSV BOM incluido** — Compatibilidad Excel

---

## Referencia: archivos proyecto relacionados

| Archivo | Contenido |
|---------|----------|
| `core/infra_core/encoding.py` | Fallback cadena CJK, reparación CP437 mojibake |
| `core/schema_core/schema_migrate_steps_29.py` | Manera correcta comilla FTS5 tokenchars |
| `core/tools/fs_dialog.py` | Diálogo selección carpeta decodificación CP932 |
| `core/configuration/json_rw.py` | config.json backslash reparación |
| `routes/collections.py` | CSV exportación BOM agregar |
| `CLAUDE.md` | Sección "Nota Windows > Salida consola" |
