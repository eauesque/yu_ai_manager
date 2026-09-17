# Informe de Benchmark de Rendimiento de Búsqueda Regex

**Fecha de encuesta:** 2026-02-23
**Escala objetivo:** 276,000 archivos / tabla de plantillas

---

## Descripción General

Este benchmark se realizó para verificar la viabilidad práctica de la búsqueda regex de YU AI Manager (`tag_query_regex=true`) en una base de datos a gran escala (276K+ registros).

Hay dos rutas de implementación de búsqueda:

| Ruta | Ubicación | Método |
|------|------|------|
| API WebUI | `core/query/filters_tags.py` | Operador SQL `REGEXP` (+ alternancia de Python) |
| Herramienta CLI | `tools/regex_debug.py` | Escaneo completo de `re.search()` de Python |

---

## Arquitectura

### Flujo de Regex de API WebUI

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Fragmento SQL generado:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` se prepende automáticamente al patrón para búsquedas insensibles a mayúsculas
- El sistema se retrocede a `LIKE %pattern%` en entornos donde `REGEXP` no se soporta

### Flujo de Herramienta CLI (`regex_debug.py`)

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Cargar todos los registros en memoria
# -> Filtrado secuencial con Python re.search()
```

---

## Resultados de Benchmark (Valores de Referencia)

> **Nota:** Los valores a continuación son estimaciones basadas en mediciones reales usando `tools/regex_debug.py`.
> Varían significativamente dependiendo del hardware y estado de caché de BD.

### Escaneo Completo de CLI (Python `re.search`)

| Recuento de registros | Inicio en frío | Caliente (caché del SO) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### API WebUI (SQL REGEXP)

El enlace SQLite de Python (módulo `sqlite3`) no implementa `REGEXP` de forma predeterminada. Es necesario registrar el módulo `re` de Python usando `con.create_function("regexp", 2, ...)`.

Después del registro, se invoca una devolución de llamada de Python para cada fila, por lo que el rendimiento es comparable al escaneo de CLI (lineal en el recuento de registros).

---

## Análisis de Cuello de Botella

| Factor | Impacto | Mitigación |
|------|------|------|
| Obtención de fila completa (escaneo de Python) | Alto | El indexación no es posible (regex es incompatible con B-Tree) |
| Longitud promedio de raw_prompt | Medio | Los prompts más largos aumentan el costo de `re.search()` |
| Efecto de caché | Alto | Ejecuciones posteriores tienen casi cero I/O debido a caché de página del SO |
| Contención de FTS5 | Bajo | El índice FTS usa una ruta separada de regex cuando `enable_fts=true` |
| MMAP (30GB) | Positivo | Ya configurado en `schema_connect.py`, reduce gastos generales de I/O |

---

## Configuración Actual de MMAP / PRAGMA

De `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # Caché de 64 MB
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # mmap de 30 GB
```

El `get_db()` de WebUI (`db_state.py`) solo establece WAL + NORMAL sin mmap.
Añadir configuración de mmap a la conexión de búsqueda podría mejorar el rendimiento de inicio en frío.

---

## Mejoras Recomendadas

### Corto Plazo (Solo Cambios de Configuración)

1. **Añadir mmap a `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Registrar la función `REGEXP`** (dentro de `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Medio Plazo (Cambios de Implementación)

| Enfoque | Descripción | Efecto |
|------|------|------|
| Prefiltro `MATCH` de FTS5 | Estrechar candidatos con FTS antes de regex | Aceleración significativa para ciertos patrones |
| Búsqueda en fondo + Server-Sent Events | Transmitir resultados incrementalmente | Mejora de UX (elimina espera de primer resultado) |
| Caché de búsqueda (TTL 30s) | Respuesta instantánea para patrones idénticos repetidos | Efectivo para búsquedas repetidas |

---

## Procedimiento de Medición de CLI

```bash
# Medición básica
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Medición con tiempo (comando bash time)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Específica de campo
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Salida de ejemplo (suponiendo 276,000 registros):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Resumen

- Un escaneo de regex completo de 276,000 registros toma aproximadamente **6-10 segundos en frío, 2-3 segundos en caliente**
- Añadir `PRAGMA mmap_size` y registro de función `REGEXP` debe mejorar la capacidad de respuesta
- Regex no puede usar índices B-Tree, por lo que escala linealmente con recuento de registros
- Un prefiltro FTS5 es la mejora de medio plazo más efectiva
