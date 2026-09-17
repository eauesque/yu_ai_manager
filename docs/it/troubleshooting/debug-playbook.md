# Manuale di Debug di YU AI Manager

## Avvio Rapido

```bash
# Esecuzione diagnostica completa
python debug_check.py

# Specificare DB
python debug_check.py --db /path/to/tags.db

# Controllo rapido (salta sintassi/Extension)
python debug_check.py --quick
```

---

## Problemi Comuni e Soluzioni

### 1. config.json corrotto (problema backslash)

**Sintomo:** JSONDecodeError all'avvio del server
**Causa:** Backslash come `\U`, `\w` ecc. diventano escape non validi nell'inserimento manuale di percorsi Windows
**Soluzione:** Viene riparato automaticamente all'avvio del server. Per riparazione manuale:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all salta alcune cartelle

**Sintomo:** "Scansione tutte le cartelle" non elabora alcune cartelle
**Procedura di verifica:**
```bash
# Verifica contenuto scan_roots
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Punti da verificare:**
- Il percorso non è troppo corto?
- Non c'è `\` finale?
- `os.path.exists(path)` restituisce True?

### 3. Condivisione QR "Nessun contenuto"

**Sintomo:** Pulsante condivisione QR → Positivo/Negativo vuoti
**Cause possibili:**
1. Nessun record nella tabella `templates` (meta_source=unknown)
2. Mismatch chiave nella risposta API (corretto in v2.7.0)

**Verifica:**
```bash
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # ID problematico
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Fallimento scansione con percorsi WSL/UNC

**Sintomo:** Fallimento probe con percorso `\\wsl.localhost\...`
**Verifica:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'repr: {repr(path)}')
"
```
**Nota:** `pathlib.Path.exists()` ha un bug con i percorsi UNC WSL. Usare `os.path.exists()`.

### 5. Extension non caricata

**Sintomo:** Non appare nella lista Extension
**Verifica:**
```bash
python debug_check.py  # Vedere la sezione Extension check
```
**Punti da verificare:**
- Esiste `extension.json` o `extension.yml`?
- JSON/YAML è valido?
- Esiste il campo `name`?

### 6. Bloccato fuori dall'autenticazione PIN

**Sintomo:** 5 fallimenti → blocco per 60 secondi
**Soluzione:** Attendere 60 secondi. O resettare con riavvio del server.

### 7. Verifica QR / Bundle della pagina di errore 500

**Sintomo:** L'intera pagina diventa 500 e viene mostrata la pagina di errore dedicata

**Punti minimi da verificare:**
- Nella schermata compare un QR code
- Viene visualizzato il pulsante `Copia Bundle JSON`
- Viene visualizzato il pulsante `Scarica Bundle (.json.gz)`
- All'URL del QR si vede `AI Error Bundle`

**Procedure di verifica:**
```bash
# Prima avviare il server normalmente
venv\Scripts\python.exe web_ui.py
```

1. Nel browser, eseguire l'operazione che intenzionalmente causa l'errore 500
2. Verificare che nella pagina di errore 500 compaiano il QR e i pulsanti Bundle
3. Premere `Copia Bundle JSON` e verificare che il JSON contenga `schema`, `error_id`, `request`, `error`, `state`

**File correlati:**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`

---

## Come Leggere il Log del Server

### Output Console Server

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → La riparazione automatica dei backslash di config.json è stata eseguita

[DEBUG] scan/start: raw=..., sanitized=...
  → Percorso all'avvio della scansione (valore grezzo → dopo sanitizzazione)

[DEBUG] scan-all root 0: repr=..., len=...
  → Dettagli di ogni percorso root nella scansione di tutte le cartelle

[Scan] Auto-registered scan root: /path/to/dir
  → Registrazione automatica al successo della scansione

[ERROR] file.json: JSON parse failed: ...
  → Errore di parsing in safe_load_json (l'app non crasha)
```

---

## Struttura File e Target di Debug

```
web_ui.py          ← Entry point (avvio server)
core/
  config.py        ← Gestione configurazione
  server.py        ← Autenticazione PIN
  scanner.py       ← Motore di scansione
  extensions.py    ← Caricamento Extension
  db.py            ← Gestione connessione DB
routes/
  scan.py          ← API scansione
  search.py        ← API ricerca
  share.py         ← API condivisione QR
  debug.py         ← API debug
  server_info.py   ← API server-info / error-report enrich
core/web/
  error_handlers.py ← Pagina errore 500 + generazione bug report QR
  error_bundle.py   ← Generazione / riduzione / arricchimento error bundle
  request_hooks.py  ← Aggiunta X-Request-Id
ui/default/templates/
  error.html       ← UI Copy / Download pagina errore 500
src/ts/shared/
  error-reporter.ts ← Error reporter client-side per fallimenti parziali
```
