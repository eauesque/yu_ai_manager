# Insidie dell'Encoding CJK / Caratteri a 2 Byte e Contromisure

Questo documento riassume i bug specifici dell'ambiente a 2 byte, incentrato sul giapponese (CP932/Shift-JIS), e le soluzioni adottate in questo progetto. È inteso come riferimento per sviluppatori e agenti AI che incontrano problemi simili.

---

## 1. Crash CP932 della Console Windows

### Sintomo

Il default dell'encoding di output di `cmd.exe` / PowerShell / Git Bash di Windows è **CP932 (Shift-JIS)**. Se si stampa con `print()` un carattere Unicode non presente in CP932, si ottiene immediatamente un crash con `UnicodeEncodeError`.

```
UnicodeEncodeError: 'charmap' codec can't encode character '—' in position 12
```

### Esempi di Caratteri che Causano Problemi

| Carattere | Nome | Dove usato |
|-----------|------|------------|
| `—` (U+2014) | em dash | Separatore output log |
| `–` (U+2013) | en dash | Visualizzazione avanzamento |
| `✓ ✗ ✅ ❌ ⚠️` | Segni di spunta, emoji | Visualizzazione successo/fallimento |
| `🧹 📦 📁 🔍 🔧` | Emoji | Visualizzazione contenuto elaborazione |
| `█ ░` | Caratteri blocco | Barra di avanzamento |

### Contromisure

- **In `print()` usare solo caratteri ASCII**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-` ecc.
- Impostare `PYTHONIOENCODING=utf-8` risolve il problema, ma poiché dipende dall'ambiente dell'utente è più sicuro avvicinarsi all'ASCII in modo difensivo

### Ambito di Impatto

In questo progetto sono stati corretti in batch **19 file** (v2.28.0). Poiché l'AI (Claude/GPT) usa emoji e em dash con alta probabilità, questo è **uno dei punti a cui prestare maggiore attenzione nella revisione del codice generato da AI**.

---

## 2. Mojibake nei Nomi File ZIP (CP437 mojibake)

### Sintomo

I file ZIP creati con Windows vecchi (era 95/98/XP) memorizzano i nomi file in **Shift-JIS (CP932)**, ma la specifica ZIP non ha informazioni sull'encoding. Python `zipfile` decodifica come **CP437** quando il bit 11 (flag UTF-8) non è impostato, risultando in nomi file giapponesi come `âwâCâèâb`.

### Contromisura: Catena di Fallback a 10 Livelli

Definire un elenco di priorità degli encoding CJK in `core/infra_core/encoding.py`:

```
UTF-8 (tentato prima da zipfile) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- **Non usare** `chardet` / `cchardet`: Per nomi file brevi (10-30 byte) i falsi positivi sono troppo numerosi
- Il metodo a ordine fisso ha maggiore riproducibilità ed è più facile da debuggare

### Parametro `metadata_encoding` di Python 3.11+

```python
# Con Python 3.11+ è possibile specificare direttamente con metadata_encoding
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

---

## 3. Blocco della Scansione con Caratteri a 2 Byte in ZIP/7z

### Sintomo

`zipfile.ZipFile()` a volte entra in I/O bloccante a certi byte durante la lettura della directory centrale di vecchi ZIP con encoding Shift-JIS, causando il blocco.

### Contromisura

1. **Protezione timeout**: Introduzione di helper thread daemon `run_with_timeout()`
   - Recupero lista file (listing): 30 secondi
   - Scansione I/O: 60 secondi
2. **Tabella scan_errors** (migration v24): Registrazione persistente nel DB di timeout ed errori di encoding

---

## 4. Problema delle Virgolette in SQLite FTS5 tokenchars

### Sintomo

Usando l'opzione `tokenchars` nella direttiva `tokenize` di SQLite FTS5, le combinazioni di virgolette causano errori di parsing.

```sql
-- NG: virgolette singole esterne + doppie interne → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK: virgolette doppie esterne + singole interne
tokenize="unicode61 tokenchars '_:.'"
```

### Contromisura

Usare la distinzione tra triple-quote lato Python:

```python
# OK: usare sia " che ' di SQL dentro ''' di Python
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

---

## 5. Encoding UTF-16 di EXIF WebP

### Sintomo

Alcuni strumenti di generazione immagini (in particolare NAI) memorizzano i metadati EXIF di WebP codificati in **UTF-16 (con BOM)**. La normale decodifica UTF-8 produce mojibake.

### Contromisura

- Rilevare il BOM (Byte Order Mark) per determinare UTF-16 BE/LE
- Se non c'è BOM, stimare BE/LE con euristica
- Come fallback, provare in ordine UTF-8 → latin-1

---

## 6. Encoding dei Chunk tEXt di PNG

### Sintomo

La specifica PNG definisce i chunk tEXt come **Latin-1 (ISO-8859-1)**, ma molti strumenti di generazione immagini AI memorizzano le stringhe codificate UTF-8 così come sono. Decodificando con `latin-1` il giapponese risulta in mojibake.

### Contromisura

Decodificare con priorità UTF-8, fallback a latin-1 in caso di fallimento:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Backslash nei Percorsi Windows in config.json

### Sintomo

Poiché i percorsi file di Windows contengono backslash (`\`), scrivere manualmente i percorsi in un file JSON genera sequenze di escape non valide.

```json
{"scan_roots": ["C:\Users\test"]}  // \U e \t vengono interpretati come sequenze di escape
```

### Contromisura

- Riparazione automatica all'avvio del server con `_repair_json_backslashes()`

---

## 8. pathlib e Percorsi UNC WSL

### Sintomo

Su WSL (Windows Subsystem for Linux), `pathlib.Path.exists()` a volte restituisce risultati errati per i percorsi UNC (`\\server\share\...`).

### Contromisura

- Usare `os.path.exists()` per verificare l'esistenza dei percorsi UNC
- `pathlib` è comodo ma ha scarsa affidabilità sui percorsi di rete

---

## 9. UTF-8 BOM nell'Export CSV

### Sintomo

Aprendo file CSV UTF-8 con Excel, senza BOM si verifica il mojibake. Excel interpreta UTF-8 senza BOM come ANSI (CP932 in ambiente giapponese).

### Contromisura

```python
buf.write("﻿")  # UTF-8 BOM for Excel compatibility
```

Aggiungere BOM (`﻿`) all'inizio del CSV.

---

## 10. `ensure_ascii=False` in JSON

### Sintomo

Python `json.dumps()` di default esegue l'escape dei caratteri non ASCII come `\uXXXX`. Se le risposte dei tool MCP hanno nomi tag giapponesi o percorsi file escaped come `タグ`, l'agente AI ha difficoltà a comprenderne il contenuto.

### Contromisura

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

In questo progetto usato uniformemente in tutti i moduli tool MCP (10 file).

---

## 11. Decodifica Output del Dialogo di Selezione Cartelle

### Sintomo

Quando si chiama un dialogo di selezione cartelle con PowerShell in Windows, l'output di `subprocess` è codificato in CP932.

### Contromisura

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

---

## Note per gli Agenti AI

Molti dei problemi sopra descritti sono **pattern che l'AI tende a trascurare quando genera codice**:

1. **Non usare emoji o caratteri decorativi in `print()`** — L'AI li usa con alta probabilità per rendere più accattivante l'output
2. **Non assumere l'encoding dei nomi file** — Scrivendo con presupposto UTF-8, si rompe in ambienti CP932
3. **I test reali sono obbligatori per le virgolette SQLite** — Ci sono casi in cui non funziona anche se sembra corretto dalla documentazione
4. **`json.dumps()` con `ensure_ascii=False`** — Obbligatorio per gestire dati giapponesi
5. **Decodificare l'output di subprocess con l'encoding dell'ambiente** — Windows ha spesso CP932
6. **Il CSV deve avere il BOM** — Per compatibilità con Excel

## Problema

DB sorting giapponese caratteri non funziona:
```sql
SELECT * FROM files ORDER BY filename COLLATE NOCASE;
-- Risultati: A, B, Z, あ, い (NOCASE non ordina CJK)
```

## Causa

NOCASE collation è ASCII-only.
CJK richiedono collation dedicata.

## Soluzione

Usa UNICODE collation:

```sql
SELECT * FROM files ORDER BY filename COLLATE UNICODE;
```

## Frontend

JavaScript sorting (preferito):

```javascript
files.sort((a, b) => 
  a.filename.localeCompare(b.filename, 'ja-JP')
);
```

## Migration

Se database creato con NOCASE:

```python
# Backup first
import shutil
shutil.copy('tags.db', 'tags.db.backup')

# Rebuild indici
db.execute('REINDEX')
```

## Best practice

- Sempre specifica COLLATE UNICODE per CJK
- Test con dataset reale (hiragana, kanji mix)
- Considera locale-specific collation

## Versioni fixed

v4.88.0+ dove collation default è UNICODE.
