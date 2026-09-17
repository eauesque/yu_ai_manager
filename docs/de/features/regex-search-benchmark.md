# Regex-Such-Leistungs-Benchmark-Bericht

**Umfragedatum:** 2026-02-23
**Zielmaßstab:** 276.000 Dateien / Templates Tabelle

---

## Übersicht

Dieser Benchmark wurde durchgeführt, um die praktische Machbarkeit der Regex-Suche von YU AI Manager (`tag_query_regex=true`) auf einer großmaßstäblichen Datenbank (276K+ Datensätze) zu überprüfen.

Es gibt zwei Such-Implementierungs-Pfade:

| Pfad | Ort | Methode |
|------|------|------|
| WebUI-API | `core/query/filters_tags.py` | SQL `REGEXP` Operator (+ Python Fallback) |
| CLI-Tool | `tools/regex_debug.py` | Python `re.search()` Vollständiger Scan |

---

## Architektur

### WebUI-API Regex-Fluss

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Generiertes SQL-Fragment:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` wird automatisch dem Muster für Groß-/Kleinschreibungs-insensitive Suchen vorangestellt
- Das System fällt auf `LIKE %pattern%` in Umgebungen zurück, in denen `REGEXP` nicht unterstützt wird

### CLI-Tool (`regex_debug.py`) Fluss

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Alle Zeilen in den Speicher laden
# -> Sequenzielle Filterung mit Python re.search()
```

---

## Benchmark-Ergebnisse (Referenzwerte)

> **Hinweis:** Die Werte unten sind Schätzungen basierend auf tatsächlichen Messungen mit `tools/regex_debug.py`. Sie variieren erheblich je nach Hardware und DB-Datei-Cache-Zustand.

### CLI Vollständiger Scan (Python `re.search`)

| Datensatz-Anzahl | Kalter Start | Warm (OS Cache) |
|------|-----------|-----------------|
| 10.000 | ~0,3s | ~0,1s |
| 100.000 | ~2,5s | ~0,8s |
| 276.000 | **~6-10s** | **~2-3s** |

### WebUI-API (SQL REGEXP)

Das SQLite Python Binding (`sqlite3` Modul) implementiert `REGEXP` standardmäßig nicht. Es ist notwendig, Pythons `re` Modul mit `con.create_function("regexp", 2, ...)` zu registrieren.

Nach der Registrierung wird für jede Zeile ein Python-Callback aufgerufen, daher ist die Leistung mit dem CLI-Scan vergleichbar (linear in der Datensatzanzahl).

---

## Engpass-Analyse

| Faktor | Auswirkung | Entschärfung |
|------|------|------|
| Vollständiger Zeilen-Abruf (Python Scan) | Hoch | Indizierung ist nicht möglich (Regex ist mit B-Tree nicht kompatibel) |
| Durchschnittliche raw_prompt Länge | Mittel | Längere Eingabeaufforderungen erhöhen die `re.search()` Kosten |
| Cache-Effekt | Hoch | Zweiter Run onward hat fast keine I/O aufgrund des OS-Seiten-Caches |
| FTS5-Konflikte | Gering | FTS-Index verwendet einen separaten Pfad von Regex, wenn `enable_fts=true` |
| MMAP (30GB) | Positiv | Bereits in `schema_connect.py` konfiguriert, reduziert I/O-Overhead |

---

## Aktuelle MMAP / PRAGMA Einstellungen

Von `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB Cache
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

Die WebUI `get_db()` (`db_state.py`) setzt nur WAL + NORMAL ohne mmap. Das Hinzufügen von mmap-Einstellungen zur Such-Verbindung könnte die Kalt-Start-Leistung verbessern.

---

## Empfohlene Verbesserungen

### Kurzfristig (nur Konfigurationsänderungen)

1. **Fügen Sie mmap zu `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Registrieren Sie die `REGEXP` Funktion** (innerhalb `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Mittelfristig (Implementierungs-Änderungen)

| Ansatz | Beschreibung | Effekt |
|------|------|------|
| FTS5 `MATCH` Vor-Filter | Kandidaten mit FTS vor Regex eingrenzen | Erhebliche Beschleunigung für bestimmte Muster |
| Hintergrund-Suche + Server-Sent Events | Ergebnisse schrittweise streamen | UX-Verbesserung (eliminiert Wartezeit für erstes Ergebnis) |
| Such-Cache (TTL 30s) | Sofortige Antwort für wiederholte identische Muster | Wirksam für wiederholte Suchen |

---

## CLI-Messungs-Verfahren

```bash
# Grundlegende Messung
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Zeitgesteuerte Messung (bash time-Befehl)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Feld-spezifisch
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Beispiel-Ausgabe (angenommen 276.000 Datensätze):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Zusammenfassung

- Ein vollständiger Regex-Scan von 276.000 Datensätzen dauert ungefähr **6-10 Sekunden kalt, 2-3 Sekunden warm**
- Das Hinzufügen von `PRAGMA mmap_size` und `REGEXP` Funktionsregistrierung sollte die Reaktionsfähigkeit verbessern
- Regex kann B-Tree-Indizes nicht verwenden, daher skaliert sie linear mit der Datensatzanzahl
- Ein FTS5 Vor-Filter ist die effektivste mittelfristige Verbesserung
