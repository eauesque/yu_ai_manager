# Tag Database - Debug Checklist

**Debug-Liste in Prioritätsreihenfolge**
**Status**: Legacy (Protokoll aus der Ära v2.5.x; alle Punkte sind bereits erledigt)
**Letzte Aktualisierung**: 2026-02-13

---

## P0 (Critical): Sofort beheben (beeinflusst die Benutzbarkeit)

### ✅ 1. UI-Layout-Verschiebung beheben

**Problem:**
```
Suchfelder passen nicht nebeneinander,
Buttons sind verrutscht
```

**Prüfmethode:**
1. WebUI starten
2. Browser auf 1366x768 vergrößern/verkleinern
3. Anordnung der Suchzeile prüfen

**Korrekturstelle:** `templates/index.html`
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
  <!-- flex-wrap: wrap hinzufügen -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Verifikation:**
- [ ] 1920x1080 wird korrekt angezeigt
- [ ] 1366x768 wird korrekt angezeigt
- [ ] 768x1024 (Tablet) wird korrekt angezeigt

---

### ✅ 2. Duplikate in der Tag-Autovervollständigung entfernen

**Problem:**
```
Duplikate erscheinen in Autovervollständigungsvorschlägen

Beispielanzeige:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ Nur der Unterschied Leerzeichen vorhanden/nicht
```

**Prüfmethode:**
1. Im Tag-Eingabefeld "sample_creator" eingeben
2. Autovervollständigung prüfen
3. Auf Duplikate prüfen

**Korrekturstelle:** `static/js/main/main.js`
```javascript
// initTagAutocomplete() 内
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normalisieren und Duplikate entfernen
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // Leerzeichen nach Komma
      .replace(/\s+/g, ' ')        // Mehrere Leerzeichen → eines
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Count summieren
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Verifikation:**
- [ ] Keine Duplikate mehr
- [ ] Counts werden zusammengezählt
- [ ] Keine Performance-Probleme

---

## P1 (High): Verbesserung (beeinflusst Funktionen)

### ✅ 3. Test der Klammer-Normalisierung bei der Suche

**Problem:**
```
Prüfen, ob \(tag\) und (tag) äquivalent behandelt werden
```

**Prüfmethode:**
1. Bild mit Tag `\(emphasis\)` vorbereiten
2. Im Suchfeld nach `(emphasis)` suchen
3. Auf Treffer prüfen

**Prüfpunkte:**
- [ ] Suche nach `(tag)` → auch `\(tag\)` wird getroffen
- [ ] Suche nach `\(tag\)` → auch `(tag)` wird getroffen
- [ ] Im Regex-Modus keine Umwandlung

**Zugehöriger Code:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. Test des ZIP-Inhalt-Ladens

**Problem:**
```
Werden Bilder im ZIP korrekt angezeigt?
Werden Metadaten korrekt extrahiert?
```

**Testfälle:**

#### Test 1: Grundverhalten
```bash
# 1. Test-ZIP erstellen
zip test.zip image1.png image2.png

# 2. Scan
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Prüfen
python tagdb_tool.py search --db test.db --q "*"
```

**Prüfung:**
- [ ] Dateien im ZIP werden im Format `test.zip!image1.png` registriert
- [ ] Metadaten werden extrahiert
- [ ] Thumbnails werden angezeigt

#### Test 2: Entpack-Funktion
```
1. Im WebUI eine Datei im ZIP öffnen
2. Auf "Entpacken und bearbeiten" klicken
3. Prüfen, ob der Explorer geöffnet wird
4. Prüfen, ob die entpackte Datei existiert
```

**Prüfung:**
- [ ] Entpacken-Button wird angezeigt
- [ ] Klick öffnet den Explorer
- [ ] Wird in extracted/ entpackt
- [ ] Die entpackte Datei wird in der DB registriert

#### Test 3: Große ZIPs
```bash
# 1) 1.1GB ZIP erstellen (Zip64)
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

# 2) ZIP-Inhalt scannen
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Prüfung:**
- [x] Speicherverbrauch nicht auffällig hoch
- [x] Scan-Zeit innerhalb zulässiger Grenzen (unter 5 Min.)
- [x] Keine Fehler

**Messergebnis (2026-02-17):**
- ZIP-Größe: `1,153,433,914 bytes` (ca. 1,1 GB)
- Laufzeit: `elapsed=0:00.14`
- Max. RSS: `maxrss_kb=23864`
- DB-Einträge: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Test der Checkpoint-Suche

**Problem:**
```
Werden Modellnamen korrekt extrahiert und gesucht?
```

**Testfälle:**

#### Test 1: Extraktion des Modellnamens
```python
# Prüfen, ob Modellnamen aus verschiedenen Formaten extrahiert werden

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

**Prüfung:**
- [ ] Extraktion aus NovelAI-Format
- [ ] Extraktion aus SD-Format
- [ ] Extraktion aus ComfyUI-Format

#### Test 2: Suchfunktion
```
1. Im WebUI auf das Checkpoint-Eingabefeld klicken
2. Autovervollständigung prüfen
3. Nach "animagine" suchen
4. Prüfen, ob nur Bilder des entsprechenden Modells angezeigt werden
```

**Prüfung:**
- [ ] Autovervollständigung funktioniert
- [ ] Teilweise Übereinstimmung wird gefunden
- [ ] Sortierung nach Nutzungshäufigkeit

---

## P2 (Medium): Zukunftsverbesserungen (Performance)

### ✅ 6. Thumbnail-Cache implementieren

**Problem:**
```
Thumbnails von Dateien im ZIP werden jedes Mal generiert
→ langsam
```

**Implementierungsvorschlag:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Cache-Pfad generieren
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Falls Cache vorhanden, zurückgeben
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Andernfalls generieren
    thumbnail = generate_thumbnail(...)

    # In Cache speichern
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Verifikation:**
- [ ] Zweiter Zugriff ist schneller
- [ ] Speicherverbrauch akzeptabel
- [ ] Cache-Clear-Funktion vorhanden

---

### ✅ 7. Performance-Messung bei großen Datenmengen

**Testfälle:**

#### Test 1: 100.000 Dateien
```bash
# Scan-Zeit messen
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Suchzeit messen
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Ziel:**
- [ ] Scan: 50.000 Einträge/Stunde oder mehr
- [ ] Suche: unter 1 Sekunde (bei 100.000 Einträgen)

#### Test 2: WebUI-Reaktion
```
1. WebUI mit 100.000 Einträgen starten
2. Suche ausführen
3. Scrollen
```

**Prüfung:**
- [ ] Suchergebnisse werden in unter 3 Sekunden angezeigt
- [ ] Scrollen ist flüssig
- [ ] Browser friert nicht ein

---

## Test-Ausführungs-Checkliste

### Umgebungsvorbereitung
- [ ] Python 3.8+ installiert geprüft
- [ ] Abhängigkeiten installiert
- [ ] Testdaten vorbereitet (Bilder verschiedener Formate)

### Funktionstests
- [ ] ZIP-Laden
- [ ] Scan mehrerer Verzeichnisse
- [ ] Tag-Normalisierung
- [ ] Checkpoint-Suche
- [ ] Modell-Filter

### UI/UX-Tests
- [ ] Layout (mehrere Auflösungen)
- [ ] Dunkler Modus
- [ ] Tastaturkürzel
- [ ] Autovervollständigung

### Performance-Tests
- [ ] 10.000 Einträge
- [ ] 50.000 Einträge
- [ ] 100.000 Einträge
- [ ] Großes ZIP (500 MB+)

### Browser-Kompatibilität
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### OS-Kompatibilität
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Debug-Werkzeuge

### Logging aktivieren
```bash
# Am Anfang von tagdb_tool.py einfügen
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance messen
```python
import time

start = time.time()
# ... Verarbeitung ...
print(f"Time: {time.time() - start:.2f}s")
```

### Speicherverbrauch prüfen
```python
import tracemalloc

tracemalloc.start()
# ... Verarbeitung ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Erstellungsdatum:** 2026-02-13
**Priorität:** P0 → P1 → P2 in dieser Reihenfolge abarbeiten
**Hinweis:** Diese Checkliste stammt aus der Ära v2.5.x; alle aufgeführten Punkte sind bereits erledigt
