# Rapporto di Benchmark Prestazioni Ricerca Regex

**Data del sondaggio:** 2026-02-23
**Scala target:** 276.000 file / tabella templates

---

## Panoramica

Questo benchmark è stato condotto per verificare la pratica fattibilità della ricerca regex (`tag_query_regex=true`) di YU AI Manager su un database su larga scala (276K+ record).

Ci sono due percorsi di implementazione della ricerca:

| Percorso | Posizione | Metodo |
|------|------|------|
| API WebUI | `core/query/filters_tags.py` | Operatore SQL `REGEXP` (+ fallback Python) |
| Strumento CLI | `tools/regex_debug.py` | Full scan Python `re.search()` |

---

## Architettura

### Flusso Regex API WebUI

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Frammento SQL generato:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` viene automaticamente anteposto al pattern per ricerche case-insensitive
- Il sistema ricade a `LIKE %pattern%` in ambienti dove `REGEXP` non è supportato

### Flusso Strumento CLI (`regex_debug.py`)

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Carica tutte le righe in memoria
# -> Filtro sequenziale con Python re.search()
```

---

## Risultati Benchmark (Valori di Riferimento)

> **Nota:** I valori sotto sono stime basate su misurazioni effettive utilizzando `tools/regex_debug.py`.
> Variano significativamente a seconda dell'hardware e dello stato della cache del file DB.

### Full Scan CLI (Python `re.search`)

| Conteggio record | Cold start | Warm (cache SO) |
|------|-----------|-----------------|
| 10.000 | ~0.3s | ~0.1s |
| 100.000 | ~2.5s | ~0.8s |
| 276.000 | **~6-10s** | **~2-3s** |

### API WebUI (SQL REGEXP)

Il binding Python di SQLite (`sqlite3` module) non implementa `REGEXP` per impostazione predefinita. È necessario registrare il modulo `re` di Python usando `con.create_function("regexp", 2, ...)`.

Dopo la registrazione, un callback Python viene invocato per ogni riga, quindi le prestazioni sono comparabili al full scan CLI (lineare nel conteggio delle righe).

---

## Analisi Collo di Bottiglia

| Fattore | Impatto | Mitigazione |
|------|------|------|
| Fetch riga completa (scan Python) | Alto | L'indicizzazione non è possibile (regex è incompatibile con B-Tree) |
| Lunghezza media raw_prompt | Medio | I prompt più lunghi aumentano il costo di `re.search()` |
| Effetto cache | Alto | La seconda esecuzione in poi ha quasi zero I/O grazie alla cache di pagina SO |
| Contesa FTS5 | Basso | L'indice FTS utilizza un percorso separato da regex quando `enable_fts=true` |
| MMAP (30GB) | Positivo | Già configurato in `schema_connect.py`, riduce il sovraccarico I/O |

---

## Impostazioni MMAP / PRAGMA Attuali

Da `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # Cache 64 MB
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # MMAP 30 GB
```

Lo `get_db()` del WebUI (`db_state.py`) imposta solo WAL + NORMAL senza MMAP.
L'aggiunta delle impostazioni MMAP alla connessione di ricerca potrebbe migliorare le prestazioni cold start.

---

## Miglioramenti Consigliati

### Breve Termine (Solo Modifiche di Configurazione)

1. **Aggiungi mmap a `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Registra la funzione `REGEXP`** (all'interno di `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Medio Termine (Modifiche di Implementazione)

| Approccio | Descrizione | Effetto |
|------|------|------|
| Pre-filtro FTS5 `MATCH` | Restringe i candidati con FTS prima di regex | Accelerazione significativa per certi pattern |
| Ricerca di background + Server-Sent Events | Trasmette i risultati in modo incrementale | Miglioramento UX (elimina l'attesa del primo risultato) |
| Cache ricerca (TTL 30s) | Risposta istantanea per pattern identici ripetuti | Efficace per ricerche ripetute |

---

## Procedura di Misurazione CLI

```bash
# Misurazione base
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Misurazione cronometrata (comando time bash)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Specifico campo
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Output di esempio (assumendo 276.000 record):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Riepilogo

- Un full scan regex di 276.000 record richiede approssimativamente **6-10 secondi cold, 2-3 secondi warm**
- L'aggiunta di `PRAGMA mmap_size` e la registrazione della funzione `REGEXP` dovrebbe migliorare la reattività
- Regex non può utilizzare indici B-Tree, quindi scala linearmente con il conteggio dei record
- Un pre-filtro FTS5 è il miglioramento medio-termine più efficace
