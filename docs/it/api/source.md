# API di esplorazione del codice sorgente

Un'API di sola lettura per l'esplorazione del codice sorgente del progetto.
È progettato in modo che i tool MCP e gli agenti AI esterni possono visualizzare e cercare in modo sicuro la codebase.

## Modello di sicurezza

Tre livelli di difesa garantiscono la sicurezza:

### 1. Normalizzazione del percorso (Prevenzione della traversal)

- Tutti i percorsi vengono normalizzati con `os.path.realpath()` e verificati rispetto alla root del progetto tramite corrispondenza prefisso.
- Gli attacchi di traversal come `../../etc/passwd` o `../../../Windows/System32` vengono bloccati.
- L'iniezione di byte null (`\x00`) viene anche rilevata e rifiutata.

### 2. Lista bianca delle estensioni

Estensioni di file consentite per la lettura:

| Categoria | Estensioni |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Configurazione | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Documentazione | `.md`, `.txt`, `.rst` |
| Script | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Altro | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

I seguenti file senza estensione sono specificamente consentiti: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Lista nera dei file sensibili

I file corrispondenti ai seguenti pattern vengono rifiutati:

| Pattern | Motivo |
|---------|--------|
| `config.json`, `config_*.json` | Dati di autenticazione come PIN e API Key |
| `*.env`, `.env.*` | Variabili di ambiente (segreti) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Chiavi di crittografia e certificati |
| `credentials*`, `*token*`, `*secret*` | Dati di autenticazione |
| `*.db`, `*.sqlite*` | File di database |
| `pnpm-lock.yaml`, `package-lock.json`, ecc. | File di blocco (grandi) |
| File immagine, video, font e modello | File binari |

### Cartelle bloccate

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Limiti di lettura

| Elemento | Limite |
|-------|-------|
| Dimensione file | 1 MB |
| Righe per lettura | 2.000 |
| Profondità traversal albero | 6 |
| Risultati ricerca | 50 |

---

## Endpoint

### GET /api/source/tree

Recupera un albero di directory.

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `path` | string | `""` (root) | Percorso relativo |
| `depth` | int | `3` | Profondità traversal (1-6) |

#### Risposta

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Le directory vengono visualizzate per prime, seguite dai file (ordinati per nome).
- `size` è in byte (solo file).
- `children` viene omesso una volta che la traversal raggiunge la `depth` specificata.

---

### GET /api/source/read

Leggi i contenuti del file con numeri di riga.

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `path` | string | — (richiesto) | Percorso file relativo |
| `offset` | int | `0` | Riga di inizio (basata su 0) |
| `limit` | int | `2000` | Numero massimo di righe |

#### Risposta

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` utilizza il formato `{line_number}\t{line_content}`.
- Usa `offset` + `limit` per paginare i file lunghi.

#### Esempi di errore

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Ricerca nel codice sorgente per testo.

#### Parametri

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|------|---------|-------------|
| `q` | string | — (richiesto) | Testo di ricerca (minimo 2 caratteri) |
| `glob` | string | `""` (tutti i file) | Filtro nome file (es. `*.py`) |
| `limit` | int | `30` | Numero massimo di risultati (1-50) |

#### Risposta

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- La ricerca non fa distinzione tra maiuscole e minuscole.
- `text` viene troncato a un massimo di 200 caratteri.

---

## Strumenti MCP

| Strumento | Descrizione | Parametri chiave |
|------|-------------|----------------|
| `source_tree` | Visualizza albero di directory | `path`: str = '', `depth`: int = 3 |
| `source_read` | Leggi contenuti file | `path`: str (richiesto), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Ricerca nel codice sorgente per testo | `query`: str (richiesto), `glob`: str = '', `limit`: int = 30 |

### Esempi di utilizzo con MCP

```
# Visualizza la struttura del progetto
source_tree(path="", depth=2)

# Leggi un file specifico
source_read(path="core/source_core/source_browser.py")

# Ricerca nella codebase
source_search(query="def register_blueprints", glob="*.py")
```

### Ambito e limitazione della velocità

- **Scope Fence**: Disponibile nell'ambito `read_only` (consentito in tutti i preset)
- **Budget Tracker**: Categoria `read` (nessun limite di velocità)
- **HITL Gate**: Livello 0 (nessuna approvazione richiesta)

---

## File di implementazione

| File | Ruolo |
|------|------|
| `core/source_core/source_browser.py` | Livello di sicurezza + logica aziendale |
| `routes/source_api.py` | Endpoint API Flask (Blueprint) |
| `mcp_server/source_tools.py` | Registrazione strumento MCP |
