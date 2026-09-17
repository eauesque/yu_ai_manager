# Tag Database - Checklist di Debug

**Elenco di debug in ordine di priorità**
**Stato**: legacy (registrazione dell'epoca v2.5.x, tutti gli elementi sono già stati gestiti)
**Ultimo aggiornamento**: 2026-02-13

---

## P0 (Critical): correzione immediata (impatto sull'usabilità)

### ✅ 1. Correzione disallineamento del layout UI

**Problema:**
```
Il campo di ricerca non entra disposto su una sola riga,
i pulsanti risultano disallineati
```

**Come verificare:**
1. Avviare la WebUI
2. Ridimensionare il browser a 1366x768
3. Controllare la disposizione della riga di ricerca

**Punto della correzione:** `templates/index.html`
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
  <!-- Aggiungere flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Verifica:**
- [ ] Visualizzazione corretta a 1920x1080
- [ ] Visualizzazione corretta a 1366x768
- [ ] Visualizzazione corretta a 768x1024 (tablet)

---

### ✅ 2. Rimozione duplicati nell'autocomplete dei tag

**Problema:**
```
Compaiono duplicati tra i candidati dell'autocomplete

Esempio di visualizzazione:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ Differenza solo nella presenza/assenza di spazi
```

**Come verificare:**
1. Nel campo di inserimento tag digitare "sample_creator"
2. Controllare l'autocomplete
3. Verificare la presenza di duplicati

**Punto della correzione:** `static/js/main/main.js`
```javascript
// dentro initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normalizza e rimuovi duplicati
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // Spazio dopo la virgola
      .replace(/\s+/g, ' ')        // Spazi multipli → singolo
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Somma i count
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Verifica:**
- [ ] I duplicati spariscono
- [ ] I count vengono sommati
- [ ] Nessun problema di performance

---

## P1 (High): miglioramento (impatto sulle funzionalità)

### ✅ 3. Test di normalizzazione delle parentesi in ricerca

**Problema:**
```
Verificare che \(tag\) e (tag) siano equivalenti
```

**Come verificare:**
1. Preparare un'immagine con tag `\(emphasis\)`
2. Cercare `(emphasis)` nel campo di ricerca
3. Verificare che venga trovata

**Punti di verifica:**
- [ ] Ricerca `(tag)` → trova anche `\(tag\)`
- [ ] Ricerca `\(tag\)` → trova anche `(tag)`
- [ ] In modalità regex la conversione non avviene

**Codice correlato:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. Test di lettura file all'interno di ZIP

**Problema:**
```
Verificare che le immagini dentro lo ZIP vengano visualizzate correttamente
e che i metadati vengano estratti correttamente
```

**Casi di test:**

#### Test 1: comportamento di base
```bash
# 1. Creare ZIP di test
zip test.zip image1.png image2.png

# 2. Scansione
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Conferma
python tagdb_tool.py search --db test.db --q "*"
```

**Verifica:**
- [ ] I file dentro lo ZIP sono registrati nel formato `test.zip!image1.png`
- [ ] I metadati vengono estratti
- [ ] Le miniature vengono visualizzate

#### Test 2: funzione di estrazione
```
1. Aprire nella WebUI un file dentro lo ZIP
2. Cliccare il pulsante "Estrai e modifica"
3. Verificare che si apra Esplora risorse
4. Verificare che i file estratti esistano
```

**Verifica:**
- [ ] Il pulsante di estrazione viene visualizzato
- [ ] Il click apre Esplora risorse
- [ ] L'estrazione avviene nella directory extracted/
- [ ] I file estratti vengono registrati nel DB

#### Test 3: ZIP di grande dimensione
```bash
# 1) Crea uno ZIP da 1.1GB (Zip64)
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

# 2) Scansione dentro lo ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Verifica:**
- [x] L'uso di memoria non cresce in modo anomalo
- [x] Il tempo di scansione è accettabile (entro 5 minuti)
- [x] Non vengono generati errori

**Misurazioni reali (2026-02-17):**
- Dimensione ZIP: `1,153,433,914 bytes` (circa 1.1GB)
- Tempo di esecuzione: `elapsed=0:00.14`
- RSS massimo: `maxrss_kb=23864`
- Registrazione DB: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Test di ricerca per checkpoint

**Problema:**
```
Verificare che i nomi dei modelli vengano estratti e cercati correttamente
```

**Casi di test:**

#### Test 1: estrazione del nome del modello
```python
# Verificare che il nome del modello venga estratto per ciascun formato

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

**Verifica:**
- [ ] Estrazione corretta in formato NovelAI
- [ ] Estrazione corretta in formato SD
- [ ] Estrazione corretta in formato ComfyUI

#### Test 2: funzione di ricerca
```
1. Nella WebUI cliccare il campo di inserimento checkpoint
2. Verificare che compaia l'autocomplete
3. Cercare "animagine"
4. Verificare che vengano visualizzate solo le immagini del modello in questione
```

**Verifica:**
- [ ] L'autocomplete funziona
- [ ] Ricerca per corrispondenza parziale possibile
- [ ] Ordinamento per frequenza di utilizzo

---

## P2 (Medium): gestione futura (miglioramento delle performance)

### ✅ 6. Implementazione della cache delle miniature

**Problema:**
```
La miniatura dei file dentro ZIP viene rigenerata ogni volta
→ lento
```

**Proposta di implementazione:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Genera il percorso della cache
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Se la cache esiste, restituiscila
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Altrimenti genera
    thumbnail = generate_thumbnail(...)

    # Salva nella cache
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Verifica:**
- [ ] Il secondo accesso è più veloce
- [ ] L'uso del disco resta entro limiti accettabili
- [ ] Funzione di pulizia della cache

---

### ✅ 7. Misura delle performance con grandi quantità di dati

**Casi di test:**

#### Test 1: 100.000 file
```bash
# Misura del tempo di scansione
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Misura del tempo di ricerca
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Obiettivo:**
- [ ] Scansione: 50.000 record/ora o più
- [ ] Ricerca: entro 1 secondo (su 100.000 record)

#### Test 2: reattività della WebUI
```
1. Avviare la WebUI con un DB da 100.000 record
2. Eseguire una ricerca
3. Scorrere
```

**Verifica:**
- [ ] I risultati di ricerca vengono visualizzati entro 3 secondi
- [ ] Lo scorrimento è fluido
- [ ] Il browser non si blocca

---

## Checklist di esecuzione dei test

### Preparazione dell'ambiente
- [ ] Conferma installazione Python 3.8+
- [ ] Installazione dei pacchetti dipendenti
- [ ] Preparazione dei dati di test (immagini di ciascun formato)

### Test funzionali
- [ ] Lettura ZIP
- [ ] Scansione di directory multiple
- [ ] Normalizzazione dei tag
- [ ] Ricerca checkpoint
- [ ] Filtro modelli

### Test UI/UX
- [ ] Layout (risoluzioni multiple)
- [ ] Dark mode
- [ ] Scorciatoie da tastiera
- [ ] Autocomplete

### Test di performance
- [ ] 10.000 record
- [ ] 50.000 record
- [ ] 100.000 record
- [ ] ZIP di grande dimensione (500MB+)

### Compatibilità browser
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### Compatibilità OS
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Strumenti di debug

### Abilitazione log
```bash
# Aggiungere all'inizio di tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Misura delle performance
```python
import time

start = time.time()
# ... elaborazione ...
print(f"Time: {time.time() - start:.2f}s")
```

### Verifica dell'uso di memoria
```python
import tracemalloc

tracemalloc.start()
# ... elaborazione ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Data di creazione:** 2026-02-13
**Priorità:** da gestire nell'ordine P0 → P1 → P2
**Nota:** questa checklist è stata creata all'epoca della v2.5.x; tutti gli elementi elencati sono già stati gestiti
